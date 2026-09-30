"""
The activity record: what this account did, in order.

Why this exists
---------------
Three records already exist in this project, and none of them answers "what has
this person been doing?":

* ``apps.users.security.SecurityEvent`` -- authentication only, and its extra
  columns (``is_current_session``, ``user_agent``) exist for the security page.
  Its own docstring says it is not a general audit log.
* ``apps.automation.models.Notification`` -- user-facing, suppressible by
  preference, and de-duplicated, so it is a *view* of events rather than a
  record of them.
* ``apps.ai.models.AIRun`` -- one AI provider call, which is an implementation
  detail of one action rather than the action itself.

So this is the durable, owner-scoped stream of user-initiated product actions:
a resume was uploaded, a job was analysed, a tailoring was generated. It is
written where the action completes -- the application service for tailoring,
the endpoint that owns it for an upload or an analysis -- so the record does not
depend on which caller reached the code.

Design constraints, and why
--------------------------
**Append-only.** There is no update path and no ``updated_at``. A record whose
history can be rewritten is not evidence of anything.

**Owner-scoped on the first field.** The same tenant rule as every other model
here: a row about someone's job search is never visible to another account.
Nothing exposed an endpoint in this phase, so there is no IDOR surface yet --
:class:`ActivityEvent` is written by the app, read by Django admin and asserted
by the architecture tests. The read API is a later phase's decision, and
``docs/adr/ADR-006-activity-record.md`` records that.

**No sensitive content.** ``summary`` is one line of prose about an action, not
a copy of a document, and metadata keys that look like secrets are dropped
rather than masked -- see :func:`_safe_metadata`. This is a record that a
person's own account did something, not a place to store what they uploaded.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import models

from .observability import is_sensitive_name, is_sensitive_value

logger = logging.getLogger(__name__)


class ActivityEvent(models.Model):
    """
    One thing the account did, recorded once and never edited.

    The action set is closed on purpose. Free-text actions would make the
    stream unqueryable within a release ("TAILORED", "tailored", "tailor
    generated"), which is the same argument ``Notification.kind`` makes.
    """

    RESUME_UPLOADED = "RESUME_UPLOADED"
    MASTER_RESUME_CHANGED = "MASTER_RESUME_CHANGED"
    JOB_ANALYSED = "JOB_ANALYSED"
    JOB_ANALYSIS_FAILED = "JOB_ANALYSIS_FAILED"
    TAILORING_GENERATED = "TAILORING_GENERATED"
    TAILORING_SAVED = "TAILORING_SAVED"
    APPLICATION_CREATED = "APPLICATION_CREATED"
    APPLICATION_STATUS_CHANGED = "APPLICATION_STATUS_CHANGED"

    ACTION_CHOICES = [
        (RESUME_UPLOADED, "Resume uploaded"),
        (MASTER_RESUME_CHANGED, "Master resume changed"),
        (JOB_ANALYSED, "Job analysed"),
        (JOB_ANALYSIS_FAILED, "Job analysis failed"),
        (TAILORING_GENERATED, "Tailoring generated"),
        (TAILORING_SAVED, "Tailoring saved"),
        (APPLICATION_CREATED, "Application created"),
        (APPLICATION_STATUS_CHANGED, "Application status changed"),
    ]

    #: Every action, as a set, so the recorder can reject a typo instead of
    #: writing a row nothing will ever group with.
    ACTIONS = frozenset(value for value, _label in ACTION_CHOICES)

    #: One line. Long enough for "Acme — Senior Backend Engineer", short enough
    #: that this can never become a place a document is pasted.
    MAX_SUMMARY = 200

    #: Longest metadata string kept. Metadata is for identifiers and counts.
    MAX_METADATA_VALUE = 120

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="activity_events",
    )

    action = models.CharField(max_length=48, choices=ACTION_CHOICES)

    #: The kind of thing acted on ("resume", "job", "application"), and its id.
    #: Deliberately *not* a ForeignKey: an activity record must survive the row
    #: it describes, or the history develops holes exactly when a user deletes
    #: something and wants to know what happened.
    object_type = models.CharField(max_length=32, blank=True, default="")
    object_id = models.PositiveBigIntegerField(null=True, blank=True)

    summary = models.CharField(max_length=MAX_SUMMARY, blank=True, default="")

    #: Non-sensitive scalars only. Values are coerced on the way in.
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

        indexes = [
            models.Index(
                fields=["user", "-created_at"],
                name="activity_user_time_idx",
            ),
            models.Index(
                fields=["user", "action"],
                name="activity_user_action_idx",
            ),
        ]

    def __str__(self):
        return "%s %s" % (self.user_id, self.action)

    # -- writing ---------------------------------------------------------

    @classmethod
    def record(
        cls,
        user,
        action: str,
        *,
        object_type: str = "",
        object_id=None,
        summary: str = "",
        metadata: dict | None = None,
    ) -> "ActivityEvent | None":
        """
        Append one event for ``user``, or return ``None`` if it was not written.

        Never raises. Every call site is a user action that has *already*
        succeeded, so failing the request because the history row failed would
        trade a real result for bookkeeping nobody asked for. The failure is
        logged instead, which is the difference between a lost row and a silent
        one.

        Unlike ``SecurityEvent.record`` there is no ``request`` argument, and
        that is deliberate: this record has no client-context columns, and the
        only values a request would contribute (a user agent, an IP) are
        attacker-controlled input with no use in a product history.
        """
        if user is None or not getattr(user, "is_authenticated", False):
            return None

        if action not in cls.ACTIONS:
            # A programming error rather than a runtime one. Writing the row
            # anyway would poison the stream with an action nothing groups by,
            # so it is refused noisily instead.
            logger.warning("activity.unknown_action action=%s", action)
            return None

        try:
            return cls.objects.create(
                user=user,
                action=action,
                object_type=str(object_type or "")[:32],
                object_id=_as_id(object_id),
                summary=str(summary or "")[: cls.MAX_SUMMARY],
                metadata=_safe_metadata(metadata),
            )
        except Exception:  # pragma: no cover - defensive by design
            logger.exception(
                "activity.record_failed user=%s action=%s",
                getattr(user, "pk", None),
                action,
            )
            return None


def _as_id(value):
    """Coerce an object id to an integer, or ``None``. Never raises on junk."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_metadata(metadata: dict | None) -> dict:
    """
    Keep the parts of ``metadata`` that are safe to keep.

    Two rules, and both *drop* the entry rather than masking it. A
    ``"[redacted]"`` marker sitting in a JSON column is a promise that
    something was there, which is worse than not recording the field.

    1. A key that names a secret is not stored at all. The judgement is
       :func:`apps.common.observability.is_sensitive_name`, so the log redactor
       and this recorder cannot disagree about what a secret looks like.
    2. Only scalars are stored, truncated. A nested structure is not metadata,
       it is a payload -- and a payload here would eventually be a resume.

    Identifiers and counts (job id, score, provider, status) are the point of
    the field, and every one of them passes.
    """
    safe = {}
    for name, value in (metadata or {}).items():
        key = str(name)[:48]
        if is_sensitive_name(key) or is_sensitive_value(value):
            continue
        if isinstance(value, bool) or isinstance(value, (int, float)):
            safe[key] = value
        elif isinstance(value, str):
            text = value.strip()
            if text:
                safe[key] = text[: ActivityEvent.MAX_METADATA_VALUE]
        # Anything else (list, dict, model instance) is dropped on purpose.
    return safe
