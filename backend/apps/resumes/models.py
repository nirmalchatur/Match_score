from django.conf import settings
from django.db import models


class Resume(models.Model):

    RESUME_TYPES = [
        ("MASTER", "Master"),
        ("TAILORED", "Tailored"),
    ]

    # Tenant boundary: a resume is only ever visible to its owner.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="resumes",
    )

    name = models.CharField(max_length=255)

    # Optional: a resume produced by tailoring has structured content but no
    # uploaded document yet. It is blank rather than required so a saved
    # tailoring is still a first-class Resume that the existing list/detail
    # endpoints can serve.
    file = models.FileField(
        upload_to="resumes/",
        blank=True,
    )

    resume_type = models.CharField(
        max_length=20,
        choices=RESUME_TYPES
    )

    is_master = models.BooleanField(
        default=False
    )

    profile_data = models.JSONField(
        null=True,
        blank=True
    )

    # --- Tailoring provenance -------------------------------------------
    # A tailored resume is never an edit of the master: it is a new row that
    # points back at the document it was derived from, so the master can never
    # be overwritten and the lineage stays inspectable.

    #: The master resume this was tailored from. Null for master resumes.
    source_resume = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tailored_versions",
    )

    #: The job this version targets. Null for master resumes.
    source_job = models.ForeignKey(
        "jobs.Job",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tailored_resumes",
    )

    #: The validated tailoring result, plus its validation verdict. Kept
    #: verbatim so a saved version can always be explained after the fact.
    tailoring_result = models.JSONField(
        null=True,
        blank=True
    )

    #: Which provider produced it ("ollama", "fake", ...). Non-secret
    #: identification only; no URL or credential is ever stored.
    ai_provider = models.CharField(
        max_length=50,
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    #: Set when a saved tailoring is edited, so the workspace can show when the
    #: user last touched this version.
    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class ResumeProfile(models.Model):

    resume = models.OneToOneField(
        Resume,
        on_delete=models.CASCADE,
        related_name="profile",
    )

    skills = models.JSONField(
        default=list,
        blank=True,
    )

    experience = models.JSONField(
        default=dict,
        blank=True,
    )

    education = models.TextField(
        blank=True,
    )

    projects = models.TextField(
        blank=True,
    )

    certifications = models.TextField(
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return f"Profile - {self.resume.name}"