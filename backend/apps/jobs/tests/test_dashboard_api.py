"""
Dashboard API tests.

The original assertions are preserved; the setup now creates an account and
authenticates, because the analyze endpoint is account-scoped.
"""

import json
from unittest.mock import Mock, patch

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


class AnalyzeAnyBoardTests(TestCase):
    """
    POST /api/jobs/analyze/ must accept any job link, not just Greenhouse.

    The endpoint used to call ``GreenhouseCollector.collect`` directly, so a
    Workday link came back as ``"URL is not a Greenhouse job board"`` -- a
    validation error for something the user had done nothing wrong about.
    These go through the real registry and the real adapters, with only the
    network mocked, so the routing itself is under test.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="any@e.test", email="any@e.test", password="pw-12345"
        )
        self.client.force_login(self.user)
        self.resume = Resume.objects.create(
            user=self.user, name="M", resume_type="MASTER", is_master=True
        )
        ResumeProfile.objects.create(
            resume=self.resume, skills=["Python"], experience={"total_years": 3.0}
        )

    def analyze(self, url):
        return self.client.post(
            "/api/jobs/analyze/",
            data=json.dumps({"url": url}),
            content_type="application/json",
        )

    @patch("apps.jobs.services.sources.workday.requests.get")
    def test_a_workday_link_is_analysed(self, mock_get):
        response = Mock(status_code=200)
        response.json.return_value = {
            "jobPostingInfo": {
                "title": "Platform Engineer",
                "company": "Acme",
                "location": "London",
                "jobDescription": "<ul><li>Python</li><li>Kubernetes</li></ul>",
            }
        }
        mock_get.return_value = response

        result = self.analyze(
            "https://acme.wd1.myworkdayjobs.com/en-GB/Platform_JR-1"
        )

        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()["job"]["source"], "workday")
        self.assertEqual(result.json()["job"]["title"], "Platform Engineer")

    @patch("apps.jobs.services.sources.generic.requests.get")
    def test_an_arbitrary_careers_page_is_analysed(self, mock_get):
        response = Mock(status_code=200)
        response.text = (
            "<html><head>"
            '<script type="application/ld+json">'
            '{"@type":"JobPosting","title":"Data Engineer",'
            '"description":"<p>Own the data platform end to end for the team.</p>",'
            '"hiringOrganization":{"name":"Globex"}}'
            "</script></head><body></body></html>"
        )
        mock_get.return_value = response

        result = self.analyze("https://globex.com/careers/data-engineer")

        self.assertEqual(result.status_code, 200, result.content)
        body = result.json()["job"]
        self.assertEqual(body["source"], "generic")
        self.assertEqual(body["company"], "Globex")

    @patch("apps.jobs.services.sources.generic.requests.get")
    def test_the_saved_job_is_labelled_for_the_ui(self, mock_get):
        """The badge comes from the stored column, not from re-deriving it."""
        response = Mock(status_code=200)
        response.text = (
            "<html><head><script type=\"application/ld+json\">"
            '{"@type":"JobPosting","title":"Engineer",'
            '"description":"<p>Build and maintain services for our customers.</p>"}'
            "</script></head><body></body></html>"
        )
        mock_get.return_value = response

        self.analyze("https://example.com/careers/1")
        job = Job.objects.get(user=self.user)
        self.assertEqual(job.source, "generic")

    def test_a_javascript_url_is_refused(self):
        """Never fetched, never followed: a javascript: URL is not a page."""
        result = self.analyze("javascript:alert(1)")
        self.assertEqual(result.status_code, 400)
        self.assertFalse(Job.objects.filter(user=self.user).exists())
