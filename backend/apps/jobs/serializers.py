from rest_framework import serializers

from .models import Job
from .services.skill_gap import analyze_skill_gap


class JobSerializer(serializers.ModelSerializer):

    #: Projected from the MatchEngine output already stored on the job. Read
    #: only, and never re-computed, so it cannot drift from `match_score`.
    skill_gap = serializers.SerializerMethodField()

    class Meta:
        model = Job

        fields = [
            "id",
            "url",
            "company",
            "title",
            "location",
            "description",
            "match_score",
            "match_result",
            "decision",
            "status",
            "error_message",
            "pipeline_steps",
            "created_at",
            "updated_at",
            "skill_gap",
        ]

        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "skill_gap",
        ]


    def get_skill_gap(self, obj):
        return analyze_skill_gap(obj)


class AnalyzeJobSerializer(serializers.Serializer):
    url = serializers.URLField()


class JobMatchSerializer(serializers.Serializer):

    url = serializers.URLField()

    company = serializers.CharField(
        max_length=255,
    )

    title = serializers.CharField(
        max_length=255,
    )

    location = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
    )

    jd_text = serializers.CharField()