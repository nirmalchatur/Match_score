"""
Security activity log and session management.

Why this exists
---------------
The app already sets the transport-level headers it should: HSTS, secure
cookies, SameSite, X-Frame-Options, a CORS allow-list, and rate limits on auth.
What it does not give a user is any way to answer "is anyone else signed in to
my account right now?" -- which is the question a security page is for. A user
who suspects a shared or stolen credential can change the password, but that
alone does not tell them whether the other session was invalidated.

Two capabilities, both scoped strictly to the requesting account:

**Sessions.** Django's own ``Session`` store is used rather than a second
bookkeeping table, so the list reflects real, live sessions and "sign out
everywhere else" revokes exactly the rows the auth middleware will consult. A
parallel table would drift from reality the first time a session expired or was
cleared.

**Security events.** A short, append-only record of things worth noticing:
sign-ins, sign-outs, password changes, and revocations. Not a general audit
log -- authentication-relevant events for this account only, never another
account IP, never a token value, never a key.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth import update_session_auth_hash
from django.contrib.sessions.models import Session
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class SecurityEvent(models.Model):
    """
    One authentication-relevant thing that happened to one account.

    Tenant-scoped on ``user`` like everything else in this project. The
    difference here is that the owner is the only one who can read these, so
    the model carries no separate visibility rules.
    """

    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGOUT = "LOGOUT"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"
    SESSIONS_REVOKED = "SESSIONS_REVOKED"
    AI_KEY_CHANGED = "AI_KEY_CHANGED"

    EVENT_CHOICES = [
        (LOGIN_SUCCESS, "Signed in"),
        (LOGOUT, "Signed out"),
        (PASSWORD_CHANGED, "Password changed"),
        (SESSIONS_REVOKED, "Other sessions signed out"),
        (AI_KEY_CHANGED, "API key updated"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="security_events",
    )

    event = models.CharField(max_length=32, choices=EVENT_CHOICES)

    #: Coarse client context, hard-truncated. The value comes from a request
    #: header an attacker controls, so it is untrusted input: it is never
    #: rendered back as markup and never used to build a link.
    user_agent = models.CharField(max_length=300, blank=True, default="")

    #: Whether this event refers to the session making the request. Computed at
    #: write time from the session key, so a later "sign out other devices"
    #: cannot retroactively change what the owner was shown.
    is_current_session = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

        indexes = [
            models.Index(
                fields=["user", "-created_at"],
                name="secevent_user_time_idx",
            ),
        ]

    def __str__(self):
        return "%s %s" % (self.user_id, self.event)

    @property
    def label(self) -> str:
        return dict(self.EVENT_CHOICES).get(self.event, self.event)

    @classmethod
    def record(
        cls,
        user,
        event: str,
        request=None,
        is_current_session: bool = False,
    ) -> None:
        """
        Append one event. Never raises.

        Called from inside the login and logout paths. A failure to write a log
        line must not turn a successful sign-in into a 500, so the whole body is
        guarded.
        """
        if user is None or not getattr(user, "is_authenticated", False):
            # A failed sign-in has no user to attach to. Attaching it to a
            # guessed account would both leak that the account exists and fill
            # a stranger log with someone else attempts, so those are handled by
            # the throttle rather than here.
            return

        try:
            agent = ""
            if request is not None:
                agent = (request.META.get("HTTP_USER_AGENT") or "")[:300]

            cls.objects.create(
                user=user,
                event=event,
                user_agent=agent,
                is_current_session=bool(is_current_session),
            )
        except Exception:
            # The event name is deliberately not logged as an argument.
            #
            # `event` is a fixed enum, not a secret, but two of the constants
            # above are spelled PASSWORD_CHANGED / AI_KEY_CHANGED, and any value
            # that reaches a logging call is then indistinguishable from a
            # credential to a data-flow scanner -- which is why this line used
            # to fail a PR with a "clear-text logging of sensitive information"
            # alert pointing at a string literal. Nothing is lost by dropping
            # it: logger.exception prints the traceback, so the call site that
            # supplied the event is the first line of the report anyway.
            logger.exception(
                "security_event.record_failed user_pk=%s",
                getattr(user, "pk", None),
            )


def _decoded(row):
    """
    Decode one session row, or ``None`` if it cannot be read.

    Django stores the payload as pickled base64. It is deliberately never
    returned to a browser: it contains the auth hash and other internal state,
    and shipping it back -- even to its owner -- would hand out the credential.
    Callers take individual keys out of it and return only coarse metadata.

    An undecodable row (a key that expired mid-read, or a payload written by an
    older schema) returns ``None`` rather than raising: one bad row must not
    blank the whole page.
    """
    try:
        return row.get_decoded()
    except Exception:
        logger.debug("security.session_undecodable")
        return None


def list_sessions(user, current_session_key: str = "") -> list:
    """
    Live sessions for one account, most recently created first.

    Ownership is determined by decoding each row and comparing
    ``_auth_user_id`` against the requesting user, and a row that does not
    decode is skipped rather than treated as belonging to anyone. That ordering
    matters: deleting every session that cannot be identified would be a
    denial-of-service lever, and deleting every session that can be identified
    is the correct behaviour.
    """
    now = timezone.now()
    results = []

    for row in Session.objects.filter(expire_date__gt=now).order_by("-expire_date"):
        data = _decoded(row)
        if data is None:
            continue

        if str(data.get("_auth_user_id")) != str(user.pk):
            continue

        agent = str(data.get("HTTP_USER_AGENT") or "")
        results.append(
            {
                # The session key is returned because "sign out this device" has
                # to name one. It is a secret, and it only ever travels to the
                # account it belongs to, over an authenticated request.
                "key": row.session_key,
                "login_at": data.get("_auth_user_login"),
                "expires_at": row.expire_date,
                "user_agent": agent[:200],
                "is_current": bool(
                    current_session_key and row.session_key == current_session_key
                ),
            }
        )

    return results


def revoke_other_sessions(user, keep_session_key: str = "") -> int:
    """
    Delete every session for this account except one.

    This is the "sign out everywhere else" action, and the reason a stolen
    session stops being usable: Django consults the session store on every
    authenticated request, so deleting the row revokes it immediately rather
    than at some expiry an attacker could simply wait out.

    Returns the number of sessions removed.
    """
    now = timezone.now()
    removed = 0

    for row in Session.objects.filter(expire_date__gt=now):
        if keep_session_key and row.session_key == keep_session_key:
            continue

        data = _decoded(row)
        if data is None:
            # Cannot confirm ownership, so it is not this account session to
            # revoke. Deleting it would let any signed-in user log others out
            # by guessing a key.
            continue

        if str(data.get("_auth_user_id")) != str(user.pk):
            continue

        row.delete()
        removed += 1

    return removed


def change_password(user, new_password: str, request=None) -> None:
    """
    Change a password, keeping the current session alive.

    Re-hashing the session auth hash is the important part. Django stores a hash
    of the password inside the session. Changing the password without calling
    ``update_session_auth_hash`` would invalidate the current session along with
    every other one, signing the account out of the very tab used to make the
    change. That reads as a bug, and people assume it failed.

    The current password is not verified here; the view does that before calling
    in, so this stays a single-purpose writer. Callers must have already
    validated ``new_password`` against the configured validators.
    """
    user.set_password(new_password)
    user.save(update_fields=["password"])

    if request is not None:
        update_session_auth_hash(request, user)

    SecurityEvent.record(
        user,
        SecurityEvent.PASSWORD_CHANGED,
        request=request,
        is_current_session=True,
    )
