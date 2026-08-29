from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.resumes.models import Resume


from apps.jobs.services.job_collector import JobCollector
from apps.jobs.services.job_processor import JobProcessor
from .models import Job
from .serializers import JobMatchSerializer, JobSerializer


class JobMatchView(APIView):

    def post(self, request):

        serializer = JobMatchSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        try:

            # 1. Convert API input into JobData
            collector = JobCollector()

            job_data = collector.collect({
                "url": serializer.validated_data["url"],
                "company": serializer.validated_data["company"],
                "title": serializer.validated_data["title"],
                "location": serializer.validated_data.get(
                    "location",
                    ""
                ),
                "description": serializer.validated_data[
                    "jd_text"
                ],
            })

            # 2. Process job
            job, result, created = (
                JobProcessor.process(
                    job_data
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
                    "error": "No master resume found"
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
                    "error": str(exc)
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class JobListView(APIView):

    def get(self, request):

        jobs = Job.objects.all().order_by(
            "-created_at"
        )

        serializer = JobSerializer(
            jobs,
            many=True,
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )


class JobDetailView(APIView):

    def get(self, request, pk):

        try:

            job = Job.objects.get(
                pk=pk
            )

        except Job.DoesNotExist:

            return Response(
                {
                    "error": "Job not found"
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = JobSerializer(
            job
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )