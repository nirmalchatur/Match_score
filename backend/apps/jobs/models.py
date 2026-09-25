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
    # This prevents duplicate job postings from being saved.
    url = models.URLField(unique=True)

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