from urllib.parse import urlparse

from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.automation.tasks import job_analysed
from apps.common.models import ActivityEvent
from apps.jobs.services import ats_registry
from apps.jobs.services import job_search
from apps.jobs.services.job_collector import JobCollector
from apps.jobs.services.job_processor import JobProcessor
from apps.jobs.services.sources.greenhouse import GreenhouseCollector
from apps.resumes.models import Resume

from .models import Job
from .serializers import (
    AnalyzeJobSerializer,
    JobMatchSerializer,
    JobSerializer,
)


def _record_analysis_failure(user, url, reason: str) -> None:
    """
    Note that an analysis failed, and roughly why.

    ``reason`` is an exception *class name*, never a message. A message from
    this pipeline can quote a stored job description or a resume field, and the
    activity record is deliberately not a place a document gets copied into.
    The class name is the part that is diagnostic and safe.
    """
    ActivityEvent.record(
        user,
        ActivityEvent.JOB_ANALYSIS_FAILED,
        object_type="job",
        summary=str(url or "")[:200],
        metadata={"reason": reason},
    )


class JobAnalyzeView(APIView):
    """
    Dashboard entry point for analysing any supported job URL.

    The board is chosen by :mod:`apps.jobs.services.ats_registry` from the URL
    itself, so the user does not pick a provider and does not get told a
    Workday link is "not a Greenhouse job board".
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AnalyzeJobSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        url = serializer.validated_data["url"]
        user = request.user

        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("Invalid URL")

            # Any supported board. The registry always resolves to an adapter,
            # so there is no "unsupported URL" error any more.
            job_data = ats_registry.collect(url)

            job, created = Job.objects.update_or_create(
                user=user,
                url=job_data.url,
                defaults={
                    "company": job_data.company,
                    "title": job_data.title,
                    "location": job_data.location,
                    "description": job_data.description,
                    "source": job_data.source,
                    "status": "RUNNING",
                    "error_message": "",
                    "pipeline_steps": [
                        {"name": "URL validated", "status": "complete"},
                        {"name": "Job page collected", "status": "complete"},
                        {"name": "Job details extracted", "status": "complete"},
                        {"name": "JD analyzed", "status": "running"},
                        {"name": "Skills extracted", "status": "pending"},
                        {"name": "Resume matched", "status": "pending"},
                    ],
                },
            )

            job, result, _ = JobProcessor.process(job_data, user)
            job.status = "COMPLETED" if result.get("score") is not None else "READY"
            job.error_message = ""
            job.pipeline_steps = [
                {"name": "URL validated", "status": "complete"},
                {"name": "Job page collected", "status": "complete"},
                {"name": "Job details extracted", "status": "complete"},
                {"name": "Job description extracted", "status": "complete"},
                {"name": "JD analyzed", "status": "complete"},
                {"name": "Skills extracted", "status": "complete"},
                {"name": "Resume matched", "status": "complete"},
                {"name": "Match score calculated", "status": "complete"},
            ]
            job.save(update_fields=["status", "error_message", "pipeline_steps", "match_score", "match_result", "decision"])

            # Tell the user the analysis landed. Emitted only on the completed
            # branch, and keyed on (id, status) so a re-analysis is a new event
            # while a repeated observation of the same one is not.
            job_analysed(request.user, job)

            ActivityEvent.record(
                request.user,
                ActivityEvent.JOB_ANALYSED,
                object_type="job",
                object_id=job.id,
                summary="%s — %s" % (job.company or "Job", job.title or "Role"),
                metadata={
                    "source": job.source,
                    "match_score": job.match_score,
                    "decision": job.decision,
                },
            )

            return Response(
                {
                    "job_id": job.id,
                    "status": "completed",
                    "job": JobSerializer(job).data,
                },
                status=status.HTTP_200_OK,
            )

        except (ValueError, TypeError) as exc:
            _record_analysis_failure(request.user, url, exc.__class__.__name__)
            return Response(
                {"error": str(exc), "status": "failed"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Resume.DoesNotExist:
            _record_analysis_failure(request.user, url, "Resume.DoesNotExist")
            return Response(
                {"error": "No master resume found", "status": "failed"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Resume.MultipleObjectsReturned:
            _record_analysis_failure(request.user, url, "Resume.MultipleObjectsReturned")
            return Response(
                {
                    "error": "Multiple master resumes found. Please keep only one.",
                    "status": "failed",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            _record_analysis_failure(request.user, url, exc.__class__.__name__)
            return Response(
                {"error": str(exc), "status": "failed"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class JobMatchView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        serializer = JobMatchSerializer(
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        try:

            collector = JobCollector()

            job_data = collector.collect({
                "url": serializer.validated_data["url"],
                "company": serializer.validated_data["company"],
                "title": serializer.validated_data["title"],
                "location": serializer.validated_data.get(
                    "location",
                    "",
                ),
                "description": serializer.validated_data[
                    "jd_text"
                ],
            })

            job, result, created = (
                JobProcessor.process(
                    job_data,
                    request.user,
                )
            )

            return Response(
                {
                    "job_id": job.id,
                    "created": created,
                    "match": result,
                },
                status=status.HTTP_200_OK,
            )

        except Resume.DoesNotExist:

            return Response(
                {
                    "error": "No master resume found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        except Resume.MultipleObjectsReturned:

            return Response(
                {
                    "error": (
                        "Multiple master resumes found. "
                        "Please keep only one."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as exc:

            return Response(
                {
                    "error": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class JobSearchView(APIView):
    """
    GET /api/jobs/search/ -- this account's jobs ranked against the resume.

    Three query parameters, all optional:

    ``q``          free text, matched against title, company and description.
    ``skills``     comma-separated skill names, OR'd with ``q`` and with each
                   other. Accepted separately because "python, django" is how
                   people think about a search, and splitting that on commas
                   server-side is more predictable than making the client build
                   a query string.
    ``limit``      capped server-side. A client asking for 10000 gets
                   MAX_RESULTS, not a database-sized response.

    Requires a master resume. A 409 with an explanatory body rather than an
    empty list, because "upload a resume first" and "nothing matched" are
    different situations and the UI has to say which one it is.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        terms = []

        free_text = (request.query_params.get("q") or "").strip()
        if free_text:
            terms.append(free_text)

        skills = (request.query_params.get("skills") or "").strip()
        if skills:
            # split() rather than a manual parse: a stray empty segment from a
            # trailing comma is harmless, and the prefilter drops it anyway.
            terms.extend(part for part in skills.split(",") if part.strip())

        try:
            raw_limit = int(request.query_params.get("limit") or 0)
        except (TypeError, ValueError):
            # A non-numeric limit is ignored rather than a 400: it is a
            # cosmetic parameter and failing the whole search over it would be
            # a poor trade.
            raw_limit = 0

        try:
            payload = job_search.search_jobs(
                user=request.user,
                terms=terms,
                limit=raw_limit or job_search.MAX_RESULTS,
            )
        except job_search.NoMasterResume:
            # The class constants, not str(exc). Two reasons, one practical and
            # one about the build: the text of a live exception is an internal
            # detail that has no business in a response body, and returning it
            # is exactly the "information exposure through an exception" shape
            # that static analysis flags on a diff. The code is what the client
            # branches on; the message is written to be read by a person.
            return Response(
                {
                    "error": job_search.NoMasterResume.MESSAGE,
                    "code": job_search.NoMasterResume.CODE,
                    "results": [],
                },
                status=status.HTTP_409_CONFLICT,
            )

        return Response(payload, status=status.HTTP_200_OK)


class JobListView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Tenant boundary: only ever this account's jobs.
        jobs = Job.objects.filter(
            user=request.user
        )

        query = request.query_params.get("q")
        status_filter = request.query_params.get("status")
        company = request.query_params.get("company")
        sort = request.query_params.get("sort", "-created_at")

        if query:
            jobs = jobs.filter(
                Q(title__icontains=query)
                | Q(company__icontains=query)
                | Q(url__icontains=query),
            )

        if status_filter:
            jobs = jobs.filter(status__iexact=status_filter)

        if company:
            jobs = jobs.filter(company__icontains=company)

        if sort not in {"-created_at", "created_at", "-match_score", "match_score"}:
            sort = "-created_at"

        jobs = jobs.order_by(sort)

        serializer = JobSerializer(
            jobs,
            many=True,
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )


class JobDetailView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):

        try:

            # Scoping the lookup prevents IDOR: a guessed pk belonging to
            # another account resolves to 404, not someone else's data.
            job = Job.objects.get(
                pk=pk,
                user=request.user,
            )

        except Job.DoesNotExist:

            return Response(
                {
                    "error": "Job not found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = JobSerializer(
            job,
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )