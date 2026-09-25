from unittest.mock import patch, MagicMock

from django.test import TestCase

from apps.jobs.models import Job
from apps.jobs.services.job_collector import JobData
from apps.resumes.models import Resume, ResumeProfile


class JobAnalyzeAPIViewTest(TestCase):
    def setUp(self):
        self.master_resume = Resume.objects.create(
            name="Master Resume",
            resume_type="MASTER",
            is_master=True,
            file="resumes/master.pdf",
        )
        self.resume_profile = ResumeProfile.objects.create(
            resume=self.master_resume,
            skills=["Python", "Django", "AWS", "SQL"],
            experience={"total_years": 5.0},
            education="Bachelor of Science in Computer Science",
            projects="Built APIs and data products",
            certifications="AWS Certified",
        )

    @patch("apps.jobs.views.GreenhouseCollector.collect")
    @patch("apps.jobs.views.JobProcessor.process")
    def test_analyze_job_endpoint_returns_job_id_and_status(
        self,
        mock_process,
        mock_collect,
    ):
        mock_collect.return_value = JobData(
            url="https://acme.greenhouse.io/jobs/123",
            company="Acme",
            title="Python Engineer",
            location="Remote",
            description="Build backend services with Python and Django.",
        )
        mock_job = Job.objects.create(
            url="https://acme.greenhouse.io/jobs/123",
            company="Acme",
            title="Python Engineer",
            location="Remote",
            description="Build backend services with Python and Django.",
            status="READY",
            match_score=88.0,
            match_result={"score": 88.0, "decision": "USE_MASTER"},
        )
        mock_process.return_value = (
            mock_job,
            {"score": 88.0, "decision": "USE_MASTER"},
            True,
        )

        response = self.client.post(
            "/api/jobs/analyze/",
            {"url": "https://acme.greenhouse.io/jobs/123"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("job_id", response.data)
        self.assertEqual(response.data["status"], "completed")
        self.assertEqual(response.data["job_id"], mock_job.id)
