from django.conf import settings
from django.db import models
from django.utils import timezone


class Application(models.Model):
    """
    One job the user is actively pursuing.

    Deliberately a thin, real row rather than a status column bolted onto
    ``Job``: a job can be tracked and never applied to, and the same job can be
    applied to more than once (for example after a re-application months later),
    so the many-to-many style record is what the data actually looks like.
    """

    #: A controlled pipeline. Kept short and specific so the tracker stays
    #: readable; each state means something a candidate can act on.
    STATUS_CHOICES = [
        ("SAVED", "Saved"),
        ("APPLIED", "Applied"),
        ("ASSESSMENT", "Assessment"),
        ("INTERVIEW", "Interview"),
        ("OFFER", "Offer"),
        ("REJECTED", "Rejected"),
        ("WITHDRAWN", "Withdrawn"),
    ]

    #: States that mean the application is finished, one way or the other.
    CLOSED_STATUSES = {"REJECTED", "WITHDRAWN", "OFFER"}

    #: Statuses that mean the candidate is waiting on the employer.
    ACTIVE_STATUSES = {"APPLIED", "ASSESSMENT", "INTERVIEW"}

    # Tenant boundary: an application is only ever visible to its owner.
    # This is the single most important field on the model.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="applications",
    )

    job = models.ForeignKey(
        "jobs.Job",
        on_delete=models.CASCADE,
        related_name="applications",
        help_text="The tracked job this application is for.",
    )

    #: The tailored version used to apply, if any. Optional: many applications
    #: are made with the master resume or an upload not tracked here.
    tailored_resume = models.ForeignKey(
        "resumes.Resume",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="applications",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="SAVED",
    )

    applied_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when the candidate first submitted an application.",
    )

    notes = models.TextField(
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["-updated_at"]

        constraints = [
            # One live application per job per account. A candidate does not
            # apply to the same posting twice; re-applying after a rejection is
            # out of scope for now and would need an explicit override.
            models.UniqueConstraint(
                fields=["user", "job"],
                name="unique_application_per_user_job",
            ),
        ]

        indexes = [
            # The tracker filters and groups by status on every page load.
            models.Index(fields=["user", "status"], name="app_user_status_idx"),
            # Detail pages and the recent list both follow updated_at.
            models.Index(fields=["user", "-updated_at"], name="app_user_updated_idx"),
        ]

    def __str__(self):
        return "%s - %s (%s)" % (
            self.job.company,
            self.job.title,
            self.get_status_display(),
        )

    @property
    def is_active(self) -> bool:
        return self.status in self.ACTIVE_STATUSES

    @property
    def is_closed(self) -> bool:
        return self.status in self.CLOSED_STATUSES

    def mark_applied(self, when=None) -> None:
        """
        Stamp ``applied_at`` on the transition into a submitted state.

        Done in the model rather than the view so the rule holds no matter
        which endpoint caused the change, and the original timestamp is never
        overwritten by a later status edit.
        """
        if self.status in {"APPLIED", "ASSESSMENT", "INTERVIEW", "OFFER"} and not self.applied_at:
            self.applied_at = when or timezone.now()
