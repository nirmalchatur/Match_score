"""
In-app notifications.

What exists before this
-----------------------
The topbar has always rendered a bell icon. It was a static ``<span>`` with no
click handler, no endpoint and no model behind it -- a placeholder for a
feature that was never built. The ``automation`` app is three zero-byte files.
So this is not a broken service being repaired; it is the service.

Design decisions worth stating
------------------------------
**A row per notification, not a counter.** A count cannot say "your tailoring
finished" and is useless the moment a user wants to know what they missed. The
list is the feature; the unread dot is a convenience derived from it.

**Read state lives on the row.** An ``is_read`` boolean plus an index means the
unread count is one indexed query rather than a scan, and "mark all read" is a
single UPDATE. A separate read-tracking table would be more normalised and
would buy nothing at this scale.

**Deduplicated on a natural key.** A status poller running every thirty seconds
would otherwise insert the same "analysis finished" row sixty times. The unique
constraint on ``(user, kind, dedupe_key)`` makes the race a no-op in the
database rather than something every call site must remember.

**No email, no push.** Deliberately browser-only. Nothing here can reach a user
who has closed the tab, which is a real limitation and is stated in the docs
rather than papered over.
"""

from django.conf import settings
from django.db import IntegrityError, models, transaction


class Notification(models.Model):
    """
    One thing that happened, worth telling the user about.

    Scoped to ``user`` on every query. The tenant boundary is the first field
    and the only one that matters: a notification records an event about
    someone's job search and must never be visible to anyone else.
    """

    #: What happened. A closed set, not free text, because the frontend maps
    #: these to an icon and a tone; an unknown value would have no
    #: presentation and would render as a blank row.
    KIND_INFO = "INFO"
    KIND_SUCCESS = "SUCCESS"
    KIND_WARNING = "WARNING"
    KIND_ERROR = "ERROR"

    KIND_CHOICES = [
        (KIND_INFO, "Information"),
        (KIND_SUCCESS, "Success"),
        (KIND_WARNING, "Warning"),
        (KIND_ERROR, "Error"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )

    kind = models.CharField(
        max_length=16,
        choices=KIND_CHOICES,
        default=KIND_INFO,
    )

    title = models.CharField(
        max_length=120,
        help_text="One line. The notification is skimmable from this alone.",
    )

    body = models.TextField(
        blank=True,
        default="",
        help_text="Optional second line of detail.",
    )

    #: Where the UI should send the user on click, e.g. "/app/jobs?job=12".
    #: Stored as a path, never a full URL, and rendered through client-side
    #: navigation -- so an attacker who can write a notification row cannot
    #: turn it into an off-site redirect.
    link = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    is_read = models.BooleanField(
        default=False,
    )

    #: Natural key for de-duplication. Empty for notifications that should
    #: never repeat (a one-off warning); set for ones a poller could emit
    #: repeatedly ("analysis finished", keyed by job id).
    dedupe_key = models.CharField(
        max_length=120,
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at", "-id"]

        constraints = [
            # Only rows that opted into de-duplication participate. A unique
            # constraint on a blank string would permit exactly one empty-key
            # row per user, which is the opposite of what "" is meant to mean.
            models.UniqueConstraint(
                fields=["user", "kind", "dedupe_key"],
                condition=models.Q(dedupe_key__gt=""),
                name="uniq_notification_dedupe",
            ),
        ]

        indexes = [
            # The bell's unread count, on every page load.
            models.Index(
                fields=["user", "is_read", "-created_at"],
                name="notif_unread_idx",
            ),
            # The list itself.
            models.Index(fields=["user", "-created_at"], name="notif_user_time_idx"),
        ]

    # ------------------------------------------------------------------
    # Read state
    # ------------------------------------------------------------------

    def __str__(self):
        return "%s: %s" % (self.user_id, self.title)

    def mark_read(self) -> bool:
        """
        Stamp ``read_at`` if unread. Returns True when it changed.

        Idempotent on purpose: the "mark all read" path and the per-row path can
        both reach the same notification, and a second call must not overwrite
        the original read time with a later one.
        """
        from django.utils import timezone

        if self.is_read:
            return False
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=["is_read", "read_at"])
        return True

    # ------------------------------------------------------------------
    # Creation helper
    # ------------------------------------------------------------------

    @classmethod
    def notify(
        cls,
        user,
        kind: str,
        title: str,
        body: str = "",
        link: str = "",
        dedupe_key: str = "",
    ):
        """
        Create one notification, or return ``None`` when it already exists.

        Returns ``None`` on a de-duplicated repeat rather than raising, so a
        call site inside a request never has to know whether it is the first
        to see the event. Ignoring the duplicate is correct: the user already
        has the notification, which is the whole intent of the key.

        The ``IntegrityError`` catch covers the race the pre-check cannot: two
        requests can both find no row and both try to insert. The constraint
        makes the second one fail, and failing *into* the desired state is a
        success, not something to log as an incident.
        """
        if user is None or not getattr(user, "is_authenticated", False):
            return None

        if dedupe_key:
            already = cls.objects.filter(
                user=user,
                kind=kind,
                dedupe_key=dedupe_key,
            ).first()
            if already is not None:
                return None

        try:
            with transaction.atomic():
                return cls.objects.create(
                    user=user,
                    kind=kind,
                    title=title[:120],
                    body=body,
                    link=link[:255],
                    dedupe_key=dedupe_key[:120],
                )
        except IntegrityError:
            return None


class NotificationPreference(models.Model):
    """
    Per-user switches for which notifications are created.

    A model rather than a settings default because the choice is personal and
    has to travel with the account. Absent row means "all defaults on", so
    signup does not have to write a row for every user.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )

    #: Job analysis finished, successfully or not.
    job_updates = models.BooleanField(
        default=True,
        help_text="Tell me when a job finishes analysing or tailoring.",
    )

    #: A new job matches the resume well.
    job_matches = models.BooleanField(
        default=True,
        help_text="Tell me when a new analysed job scores well against my resume.",
    )

    #: Application status reminders.
    application_updates = models.BooleanField(
        default=True,
        help_text="Tell me when an application changes stage.",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "notification preferences"

    def __str__(self):
        return f"notification preferences for {self.user_id}"

    @classmethod
    def for_user(cls, user):
        """The user's preferences, created on first access with defaults on."""
        obj, _ = cls.objects.get_or_create(user=user)
        return obj

    def allows(self, kind: str) -> bool:
        """
        Whether a notification of this kind should be created at all.

        A failure is suppressed only when the user has switched off *every*
        category that could produce it. Turning off job updates while leaving
        application updates on should not silence an analysis error: the user
        still wants to hear that something broke, they just do not want a note
        every time a job is re-scored.

        Unknown kinds are allowed rather than dropped. A kind added by a later
        release should reach users, and an absent preference row is a
        configuration default, not a reason to silently swallow an event.
        """
        if kind == Notification.KIND_ERROR:
            return self.job_updates or self.application_updates
        if kind == Notification.KIND_SUCCESS:
            return self.job_updates or self.job_matches
        return self.job_updates


    def __str__(self):
        return "%s: %s" % (self.user_id, self.title)

    def mark_read(self) -> bool:
        """Stamp ``read_at`` if unread. Returns True when it changed."""
        from django.utils import timezone

        if self.is_read:
            return False
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=["is_read", "read_at"])
        return True

