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
            "source",
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


class JobListSerializer(serializers.ModelSerializer):
    """
    The compact row the workspace loads for *every* job an account holds.

    Why this exists
    ---------------
    The full ``JobSerializer`` carries the posting itself (``description``,
    routinely several KB), the whole stored ``match_result``, the pipeline
    steps, the error message, and a ``skill_gap`` recomputed per row on every
    request. Measured on the real endpoint: **262 KB for 50 jobs and 2.0 MB for
    400** -- and the shell fetches that list on mount and again after every
    mutation. On a real connection the dashboard spends seconds downloading and
    parsing JSON that nothing on the list renders.

    Nothing in a list needs the posting: ``JobRow``, the sidebar search and the
    tracker render a title, a company, a location, a score and a status. The
    heavy fields are still served, by the detail endpoint, for the one job the
    user opened. That is a request for one row instead of a response carrying
    four hundred.

    Deliberately *not* a "client picks its fields" query parameter: the server
    would then have to validate which combinations are safe, and every client
    would have to be trusted to ask for the right ones. One list shape and one
    detail shape are easier to reason about and to keep user-scoped.
    """

    class Meta:
        model = Job

        fields = [
            "id",
            "url",
            "company",
            "title",
            "location",
            "source",
            "match_score",
            "decision",
            "status",
            "created_at",
            "updated_at",
        ]

        read_only_fields = fields


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