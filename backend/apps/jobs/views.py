from urllib.parse import urlparse

from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

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


class JobAnalyzeView(APIView):
    """Dashboard entry point for analyzing a Greenhouse job URL."""

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

            job_data = GreenhouseCollector.collect(url)

            job, created = Job.objects.update_or_create(
                user=user,
                url=job_data.url,
                defaults={
                    "company": job_data.company,
                    "title": job_data.title,
                    "location": job_data.location,
                    "description": job_data.description,
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

            return Response(
                {
                    "job_id": job.id,
                    "status": "completed",
                    "job": JobSerializer(job).data,
                },
                status=status.HTTP_200_OK,
            )

        except (ValueError, TypeError) as exc:
            return Response(
                {"error": str(exc), "status": "failed"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Resume.DoesNotExist:
            return Response(
                {"error": "No master resume found", "status": "failed"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Resume.MultipleObjectsReturned:
            return Response(
                {
                    "error": "Multiple master resumes found. Please keep only one.",
                    "status": "failed",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
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