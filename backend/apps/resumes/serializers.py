from rest_framework import serializers

from .models import Resume


class ResumeSerializer(serializers.ModelSerializer):

    # Derived, not stored. Both are read-only helpers for the UI.
    tailoring_summary = serializers.SerializerMethodField()
    has_documents = serializers.SerializerMethodField()

    class Meta:
        model = Resume

        fields = [
            "id",
            "name",
            "file",
            "resume_type",
            "is_master",
            "created_at",
            "updated_at",
            "source_resume",
            "source_job",
            "ai_provider",
            "tailoring_summary",
            "has_documents",
        ]

        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "source_resume",
            "source_job",
            "ai_provider",
            "tailoring_summary",
            "has_documents",
        ]

    def get_tailoring_summary(self, obj):
        """
        The validation verdict stored with a saved tailoring.

        Lets the workspace show "needs review" without shipping the whole
        tailoring payload to a list view.
        """
        if not obj.tailoring_result:
            return None
        return (obj.tailoring_result.get("validation") or {}).get("status")

    def get_has_documents(self, obj):
        """
        Whether this resume can be downloaded as DOCX/PDF.

        True for every resume, including the master: documents are rendered
        deterministically from the structured profile, so there is always
        something to produce. Exposed so the UI can decide without guessing.
        """
        return True