from django.conf import settings
from django.db import models


class Job(models.Model):

    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("RUNNING", "Running"),
        ("COMPLETED", "Completed"),
        ("FAILED", "Failed"),
        ("NEW", "New"),
        ("PROCESSING", "Processing"),
        ("READY", "Ready"),
        ("SKIPPED", "Skipped"),
    ]

    DECISION_CHOICES = [
        ("USE_MASTER", "Use Master Resume"),
        ("TAILOR", "Tailor Resume"),
        ("SKIP", "Skip"),
        ("REVIEW", "Review"),
    ]

    # Every job belongs to exactly one account. This is the tenant boundary:
    # API queries must always be scoped by this field.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="jobs",
    )

    # Prevents duplicate job postings per account. Scoped to the owner so two
    # different users can analyse the same posting independently.
    url = models.URLField()

    company = models.CharField(max_length=255)

    title = models.CharField(max_length=255)

    location = models.CharField(
        max_length=255,
        blank=True,
    )

    description = models.TextField(
        blank=True,
    )

    match_score = models.FloatField(
        null=True,
        blank=True,
    )
    match_result = models.JSONField(
        null=True,
        blank=True,
    )
    decision = models.CharField(
        max_length=50,
        choices=DECISION_CHOICES,
        blank=True,
    )

    status = models.CharField(
        max_length=50,
        choices=STATUS_CHOICES,
        default="PENDING",
    )

    error_message = models.TextField(
        blank=True,
        default="",
    )

    pipeline_steps = models.JSONField(
        default=list,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return f"{self.company} - {self.title}"

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "url"],
                name="unique_job_url_per_user",
            ),
        ]