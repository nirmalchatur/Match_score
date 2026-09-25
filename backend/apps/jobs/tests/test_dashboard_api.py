"""
Dashboard API tests.

The original assertions are preserved; the setup now creates an account and
authenticates, because the analyze endpoint is account-scoped.
"""

from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from apps.jobs.models import Job
from apps.jobs.services.job_collector import JobData
from apps.resumes.models import Resume, ResumeProfile


class JobAnalyzeAPIViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="dashboard@example.com",
            email="dashboard@example.com",
            password="dashboard-pass-123",
        )

        self.master_resume = Resume.objects.create(
            user=self.user,
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

        self.client.force_login(self.user)

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
            user=self.user,
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

    @patch("apps.jobs.views.GreenhouseCollector.collect")
    def test_analyze_job_requires_authentication(self, mock_collect):
        """The analyze endpoint must reject anonymous callers."""
        self.client.logout()

        response = self.client.post(
            "/api/jobs/analyze/",
            {"url": "https://acme.greenhouse.io/jobs/123"},
            content_type="application/json",
        )

        self.assertIn(
            response.status_code,
            [401, 403],
        )
        mock_collect.assert_not_called()

    @patch("apps.jobs.views.GreenhouseCollector.collect")
    @patch("apps.jobs.views.JobProcessor.process")
    def test_analyze_job_uses_the_authenticated_accounts_resume(
        self,
        mock_process,
        mock_collect,
    ):
        """A second account must not be able to score with someone else's resume."""
        other = User.objects.create_user(
            username="intruder@example.com",
            email="intruder@example.com",
            password="intruder-pass-123",
        )
        Job.objects.create(
            user=other,
            url="https://acme.greenhouse.io/jobs/123",
            company="Acme",
            title="Other Owner",
            location="Remote",
            description="Someone else's posting.",
        )

        mock_collect.return_value = JobData(
            url="https://acme.greenhouse.io/jobs/123",
            company="Acme",
            title="Python Engineer",
            location="Remote",
            description="Build backend services with Python and Django.",
        )
        own_job = Job.objects.create(
            user=self.user,
            url="https://acme.greenhouse.io/jobs/123",
            company="Acme",
            title="Python Engineer",
            location="Remote",
            description="Build backend services with Python and Django.",
        )
        mock_process.return_value = (
            own_job,
            {"score": 80.0, "decision": "USE_MASTER"},
            True,
        )

        self.client.post(
            "/api/jobs/analyze/",
            {"url": "https://acme.greenhouse.io/jobs/123"},
            content_type="application/json",
        )

        # The processor must be handed this request's user, never a lookup
        # of "whoever owns the master resume".
        self.assertEqual(
            mock_process.call_args[0][1],
            self.user,
        )
