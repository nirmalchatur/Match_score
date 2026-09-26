from rest_framework import serializers

from .models import Application


class JobRefSerializer(serializers.Serializer):
    """
    The slice of a job the tracker needs.

    Read-only and flattened, so the application list renders without a second
    round-trip per row and without pulling the whole JD description.
    """

    id = serializers.IntegerField()
    title = serializers.CharField()
    company = serializers.CharField()
    location = serializers.CharField(allow_blank=True)
    match_score = serializers.FloatField(allow_null=True)
    url = serializers.URLField()


class ResumeRefSerializer(serializers.Serializer):
    """Just enough of the tailored resume to label and link it."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    resume_type = serializers.CharField()
    is_master = serializers.BooleanField()


class ApplicationSerializer(serializers.ModelSerializer):
    """
    Read/write representation of an application.

    ``user`` is never writable and never read: the owner is always derived from
    the authenticated request. Accepting a ``user`` field here would be an
    invitation to file applications against somebody else's account.
    """

    job_detail = JobRefSerializer(source="job", read_only=True)
    resume_detail = ResumeRefSerializer(source="tailored_resume", read_only=True)

    class Meta:
        model = Application

        fields = [
            "id",
            "job",
            "tailored_resume",
            "status",
            "applied_at",
            "notes",
            "created_at",
            "updated_at",
            "job_detail",
            "resume_detail",
        ]

        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "applied_at",
        ]


    def validate(self, attrs):
        """
        Reject a second application for the same job.

        The database enforces this with a UniqueConstraint, but DRF only
        derives a uniqueness check from ``unique_together``. Without this the
        duplicate escapes validation and surfaces as an IntegrityError -- a 500
        for what is really a 400.
        """
        job = attrs.get("job")
        request = self.context.get("request")

        if job is not None and request is not None:
            duplicate = Application.objects.filter(
                user=request.user, job=job
            ).exists()
            if duplicate:
                raise serializers.ValidationError(
                    {"job": ["You already have an application for this job."]}
                )

        return attrs

    def validate_job(self, value):
        """
        The job must belong to the caller.

        Validated here rather than trusted, so a create cannot attach someone
        else's job. Returns 400 (a bad reference) rather than 404, which is the
        right signal: the payload is malformed, not merely unauthorised.
        """
        request = self.context.get("request")
        if request is not None and value.user_id != request.user.id:
            raise serializers.ValidationError("That job does not belong to you.")
        return value

    def validate_tailored_resume(self, value):
        """Same rule for the attached resume version."""
        if value is None:
            return value

        request = self.context.get("request")
        if request is not None and value.user_id != request.user.id:
            raise serializers.ValidationError("That resume does not belong to you.")
        return value
