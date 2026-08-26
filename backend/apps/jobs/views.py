from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.resumes.models import Resume
from apps.resumes.services.parser import ResumeParser
from apps.resumes.services.resume_profile import ResumeProfile

from apps.jobs.services.jd_profile import JDProfile
from apps.jobs.services.match_engine import MatchEngine

from .models import Job
from .serializers import JobMatchSerializer


class JobMatchView(APIView):

    def post(self, request):

        serializer = JobMatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        resume_id = serializer.validated_data["resume_id"]
        url = serializer.validated_data["url"]
        company = serializer.validated_data["company"]
        title = serializer.validated_data["title"]
        location = serializer.validated_data.get("location", "")
        jd_text = serializer.validated_data["jd_text"]

        try:
            # 1. Get master resume
            resume = Resume.objects.get(
                id=resume_id,
                is_master=True,
            )

            # 2. Parse resume
            resume_text = ResumeParser.extract_text(
                resume.file.path
            )

            # 3. Build resume profile
            resume_profile = ResumeProfile.build(
                resume_text
            )

            # 4. Build JD profile
            jd_profile = JDProfile.build(
                jd_text
            )

            # 5. Calculate match
            result = MatchEngine.calculate(
                resume_profile,
                jd_profile,
            )

            # 6. Save job
            job, created = Job.objects.update_or_create(
                url=url,
                defaults={
                    "company": company,
                    "title": title,
                    "location": location,
                    "description": jd_text,
                    "match_score": result["score"],
                    "decision": result["decision"],
                    "status": "READY",
                },
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
                    "error": "Master resume not found"
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        except Exception as exc:
            return Response(
                {
                    "error": str(exc)
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
from .models import Job
from .serializers import JobSerializer


class JobListView(APIView):

    def get(self, request):

        jobs = Job.objects.all().order_by("-created_at")

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
            job = Job.objects.get(pk=pk)
        except Job.DoesNotExist:
            return Response(
                {"error": "Job not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = JobSerializer(job)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )