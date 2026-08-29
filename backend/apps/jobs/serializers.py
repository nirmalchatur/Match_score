from rest_framework import serializers

from .models import Job


class JobSerializer(serializers.ModelSerializer):

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
            "decision",
            "status",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]


class JobMatchSerializer(serializers.Serializer):

    url = serializers.URLField()

    company = serializers.CharField(
        max_length=255
    )

    title = serializers.CharField(
        max_length=255
    )

    location = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True
    )

    jd_text = serializers.CharField()