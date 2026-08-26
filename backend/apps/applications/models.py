from django.db import models
from jobs.models import Job
from resumes.models import Resume


class Application(models.Model):

    STATUS_CHOICES = [
        ("READY", "Ready"),
        ("REVIEW", "Review"),
        ("APPROVED", "Approved"),
        ("SUBMITTING", "Submitting"),
        ("APPLIED", "Applied"),
        ("FAILED", "Failed"),
    ]

    job = models.OneToOneField(
        Job,
        on_delete=models.CASCADE,
        related_name="application"
    )

    resume = models.ForeignKey(
        Resume,
        on_delete=models.PROTECT,
        related_name="applications"
    )

    status = models.CharField(
        max_length=50,
        choices=STATUS_CHOICES,
        default="READY"
    )

    applied_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.job} - {self.status}"