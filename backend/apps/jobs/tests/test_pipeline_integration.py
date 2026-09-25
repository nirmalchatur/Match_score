"""
Integration tests for GreenhouseCollector -> JobProcessor pipeline.

Tests the full flow:
GreenhouseCollector.collect(url) -> JobData -> JobProcessor.process() -> Job model
"""

from unittest.mock import patch, MagicMock
import json

from django.test import TestCase
import requests

from django.core.exceptions import ObjectDoesNotExist

from apps.jobs.models import Job
from apps.jobs.services.sources.greenhouse import GreenhouseCollector
from apps.jobs.services.job_processor import JobProcessor
from apps.resumes.models import Resume, ResumeProfile


class GreenhouseJobProcessorPipelineTest(TestCase):
    """Integration tests for Greenhouse → JobProcessor pipeline."""

    def setUp(self):
        """Set up test data: master resume and profile."""
        # Create master resume
        self.master_resume = Resume.objects.create(
            name="Master Resume",
            resume_type="MASTER",
            is_master=True,
            file="resumes/master.pdf",
        )

        # Create resume profile with realistic data
        self.resume_profile = ResumeProfile.objects.create(
            resume=self.master_resume,
            skills=[
                "Python",
                "Django",
                "PostgreSQL",
                "AWS",
                "REST APIs",
            ],
            experience={
                "years": 3.5,
                "job_titles": [
                    "Backend Developer",
                    "Junior Backend Engineer",
                ],
            },
            education="Bachelor of Science in Computer Science",
            projects="Built several REST APIs, web scrapers, and data processing pipelines",
            certifications="AWS Solutions Architect Associate",
        )

        # Realistic Greenhouse job posting (Python backend role)
        self.python_backend_job = {
            "@type": "JobPosting",
            "title": "Senior Python Backend Engineer",
            "description": (
                "<p>We're looking for a Senior Python Backend Engineer to "
                "join our platform team.</p>"
                "<h3>Requirements:</h3>"
                "<ul><li>5+ years of Python experience</li>"
                "<li>Strong Django skills</li>"
                "<li>PostgreSQL database design</li>"
                "<li>AWS and microservices architecture</li>"
                "<li>REST API design and implementation</li></ul>"
                "<h3>Nice to have:</h3>"
                "<ul><li>Docker and Kubernetes</li>"
                "<li>CI/CD pipelines</li></ul>"
            ),
            "hiringOrganization": {
                "@type": "Organization",
                "name": "TechCorp Inc",
            },
            "jobLocation": {
                "@type": "Place",
                "address": {
                    "@type": "PostalAddress",
                    "addressLocality": "San Francisco",
                    "addressRegion": "California",
                    "addressCountry": "United States",
                },
            },
        }

        self.html_with_job = (
            "<html><body>"
            "<script type='application/ld+json'>"
            + json.dumps(self.python_backend_job)
            + "</script>"
            "</body></html>"
        )

    @patch(
        "apps.jobs.services.sources.greenhouse.requests.get"
    )
    def test_1_full_pipeline_creates_job(
        self,
        mock_get,
    ):
        """Test case 1: Full pipeline creates Job record with match data."""
        # Arrange: Mock Greenhouse HTTP response
        mock_response = MagicMock()
        mock_response.text = self.html_with_job
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        url = "https://techcorp.greenhouse.io/jobs/senior-python-backend"

        # Act: Run the pipeline
        job_data = GreenhouseCollector.collect(url)
        job, result, created = JobProcessor.process(job_data)

        # Assert: Job was created
        self.assertTrue(created)
        self.assertIsNotNone(job.id)
        self.assertEqual(job.url, url)
        self.assertEqual(job.company, "TechCorp Inc")
        self.assertEqual(job.title, "Senior Python Backend Engineer")
        self.assertIn("San Francisco", job.location)
        # Description should be clean (no HTML tags)
        self.assertNotIn("<p>", job.description)
        self.assertNotIn("<li>", job.description)
        self.assertIn("Python", job.description)
        self.assertIn("Django", job.description)

        # Assert: Match data was saved
        self.assertIsNotNone(job.match_score)
        self.assertIsNotNone(job.match_result)
        self.assertIsNotNone(job.decision)
        self.assertEqual(job.status, "READY")

        # Assert: Match result structure
        self.assertIn("score", result)
        self.assertIn("decision", result)
        self.assertIn("skills", result)
        self.assertIn("experience", result)
        self.assertIn("requirements", result)
        self.assertIn("education", result)

    @patch(
        "apps.jobs.services.sources.greenhouse.requests.get"
    )
    def test_2_update_or_create_behavior(
        self,
        mock_get,
    ):
        """Test case 2: Running same URL twice updates record, not duplicates."""
        # Arrange: Mock Greenhouse HTTP response
        mock_response = MagicMock()
        mock_response.text = self.html_with_job
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        url = "https://techcorp.greenhouse.io/jobs/senior-python-backend-v2"

        # Act: First run
        job_data_1 = GreenhouseCollector.collect(url)
        job_1, result_1, created_1 = JobProcessor.process(job_data_1)

        # Assert: First run creates
        self.assertTrue(created_1)
        job_count_after_first = Job.objects.count()

        # Act: Second run (same URL)
        job_data_2 = GreenhouseCollector.collect(url)
        job_2, result_2, created_2 = JobProcessor.process(job_data_2)

        # Assert: Second run updates, not creates
        self.assertFalse(created_2)
        self.assertEqual(job_1.id, job_2.id)  # Same Job record
        job_count_after_second = Job.objects.count()
        self.assertEqual(
            job_count_after_first,
            job_count_after_second,
        )  # No duplicate

        # Verify only one Job exists for that URL
        self.assertEqual(
            Job.objects.filter(url=url).count(),
            1,
        )

    def test_3_missing_master_resume(self):
        """Test case 3: Error when master resume doesn't exist."""
        # Arrange: Delete master resume
        self.master_resume.delete()

        # Create minimal JobData
        from apps.jobs.services.job_collector import JobData

        job_data = JobData(
            url="https://example.greenhouse.io/jobs/123",
            company="Example",
            title="Engineer",
            location="Remote",
            description="Build things",
        )

        # Act & Assert: Should raise error
        with self.assertRaises(Resume.DoesNotExist):
            JobProcessor.process(job_data)

    def test_4_missing_resume_profile(self):
        """Test case 4: Error when master resume has no profile."""
        # Arrange: Delete the profile
        self.resume_profile.delete()

        # Create minimal JobData
        from apps.jobs.services.job_collector import JobData

        job_data = JobData(
            url="https://example.greenhouse.io/jobs/123",
            company="Example",
            title="Engineer",
            location="Remote",
            description="Build things",
        )

        # Act & Assert: Should raise RelatedObjectDoesNotExist
        # (Django raises this when related object doesn't exist)
        from django.core.exceptions import ObjectDoesNotExist

        with self.assertRaises(ObjectDoesNotExist):
            JobProcessor.process(job_data)

    @patch(
        "apps.jobs.services.sources.greenhouse.requests.get"
    )
    def test_5_missing_description_fails_cleanly(
        self,
        mock_get,
    ):
        """Test case 5: Greenhouse job with missing description fails cleanly."""
        # Arrange: Mock Greenhouse response with no description
        json_ld_no_description = {
            "@type": "JobPosting",
            "title": "Engineer",
            # Missing description!
        }

        html = (
            "<html><body>"
            "<script type='application/ld+json'>"
            + json.dumps(json_ld_no_description)
            + "</script>"
            "</body></html>"
        )

        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        # Act & Assert: GreenhouseCollector should fail
        with self.assertRaises(ValueError):
            GreenhouseCollector.collect(
                "https://example.greenhouse.io/jobs/123"
            )

        # Verify no Job record was created
        self.assertEqual(Job.objects.count(), 0)

    @patch(
        "apps.jobs.services.sources.greenhouse.requests.get"
    )
    def test_6_saved_job_contains_all_data(
        self,
        mock_get,
    ):
        """Test case 6: Saved Job record contains all extracted data."""
        # Arrange: Mock Greenhouse HTTP response
        mock_response = MagicMock()
        mock_response.text = self.html_with_job
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        url = "https://techcorp.greenhouse.io/jobs/senior-python-backend-v3"

        # Act: Run pipeline
        job_data = GreenhouseCollector.collect(url)
        job, result, created = JobProcessor.process(job_data)

        # Refresh from database
        job.refresh_from_db()

        # Assert: All fields are populated correctly
        self.assertEqual(job.url, url)
        self.assertEqual(job.company, "TechCorp Inc")
        self.assertEqual(
            job.title,
            "Senior Python Backend Engineer",
        )
        self.assertIn("San Francisco", job.location)
        # Description is cleaned (no HTML)
        self.assertNotIn("<p>", job.description)
        self.assertNotIn("<h3>", job.description)
        self.assertNotIn("<ul>", job.description)
        self.assertNotIn("<li>", job.description)
        # Description still contains key content
        self.assertIn("Python", job.description)
        self.assertIn("Django", job.description)
        self.assertIn("PostgreSQL", job.description)
        self.assertIn("AWS", job.description)

        # Assert: Match data is saved
        self.assertIsNotNone(job.match_score)
        self.assertIsInstance(job.match_score, float)
        self.assertGreaterEqual(job.match_score, 0)
        self.assertLessEqual(job.match_score, 100)

        self.assertIsNotNone(job.match_result)
        self.assertIsInstance(job.match_result, dict)
        self.assertIn("score", job.match_result)
        self.assertIn("skills", job.match_result)
        self.assertIn("experience", job.match_result)
        self.assertIn("requirements", job.match_result)
        self.assertIn("education", job.match_result)

        self.assertIsNotNone(job.decision)
        self.assertIn(
            job.decision,
            ["USE_MASTER", "TAILOR", "SKIP", "REVIEW"],
        )

        self.assertEqual(job.status, "READY")


class GreenhouseJobProcessorErrorHandlingTest(TestCase):
    """Test error handling in the pipeline."""

    def setUp(self):
        """Set up test master resume."""
        self.master_resume = Resume.objects.create(
            name="Master Resume",
            resume_type="MASTER",
            is_master=True,
            file="resumes/master.pdf",
        )

        self.resume_profile = ResumeProfile.objects.create(
            resume=self.master_resume,
            skills=["Python", "Django"],
            experience={"years": 2.5},
            education="BSc Computer Science",
            projects="Various projects",
            certifications="None",
        )

    @patch(
        "apps.jobs.services.sources.greenhouse.requests.get"
    )
    def test_greenhouse_http_error_fails_gracefully(
        self,
        mock_get,
    ):
        """Greenhouse HTTP errors don't create Job records."""
        mock_get.side_effect = requests.ConnectionError(
            "Connection failed"
        )

        # Act & Assert: Should raise exception
        with self.assertRaises(requests.RequestException):
            GreenhouseCollector.collect(
                "https://example.greenhouse.io/jobs/123"
            )

        # Verify no Job was created
        self.assertEqual(Job.objects.count(), 0)

    @patch(
        "apps.jobs.services.sources.greenhouse.requests.get"
    )
    def test_invalid_greenhouse_url_fails_gracefully(
        self,
        mock_get,
    ):
        """Invalid Greenhouse URLs don't make HTTP requests."""
        # Act & Assert: Should raise ValueError before HTTP call
        with self.assertRaises(ValueError):
            GreenhouseCollector.collect(
                "https://example.com/jobs/123"
            )

        # Verify HTTP was never called
        mock_get.assert_not_called()

        # Verify no Job was created
        self.assertEqual(Job.objects.count(), 0)


class GreenhouseJobProcessorMultipleJobsTest(TestCase):
    """Test processing multiple jobs."""

    def setUp(self):
        """Set up test master resume."""
        self.master_resume = Resume.objects.create(
            name="Master Resume",
            resume_type="MASTER",
            is_master=True,
            file="resumes/master.pdf",
        )

        self.resume_profile = ResumeProfile.objects.create(
            resume=self.master_resume,
            skills=["Python", "Django", "JavaScript"],
            experience={"years": 3},
            education="BSc Computer Science",
            projects="Various projects",
            certifications="AWS Certified",
        )

    @patch(
        "apps.jobs.services.sources.greenhouse.requests.get"
    )
    def test_process_multiple_jobs(
        self,
        mock_get,
    ):
        """Process multiple jobs from different companies."""
        # Arrange: Two different job postings
        job_1_ld = {
            "@type": "JobPosting",
            "title": "Python Backend Engineer",
            "description": "Build APIs with Python and Django",
            "hiringOrganization": {"name": "Company A"},
        }

        job_2_ld = {
            "@type": "JobPosting",
            "title": "JavaScript Frontend Engineer",
            "description": (
                "Build UIs with React and JavaScript"
            ),
            "hiringOrganization": {"name": "Company B"},
        }

        url_1 = "https://companya.greenhouse.io/jobs/python-backend"
        url_2 = "https://companyb.greenhouse.io/jobs/javascript-frontend"

        # Act & Assert: Process first job
        html_1 = (
            "<html><body>"
            "<script type='application/ld+json'>"
            + json.dumps(job_1_ld)
            + "</script>"
            "</body></html>"
        )

        mock_response_1 = MagicMock()
        mock_response_1.text = html_1
        mock_response_1.raise_for_status = MagicMock()
        mock_get.return_value = mock_response_1

        job_data_1 = GreenhouseCollector.collect(url_1)
        job_1, _, created_1 = JobProcessor.process(job_data_1)

        self.assertTrue(created_1)
        self.assertEqual(job_1.url, url_1)
        self.assertEqual(job_1.company, "Company A")

        # Act & Assert: Process second job
        html_2 = (
            "<html><body>"
            "<script type='application/ld+json'>"
            + json.dumps(job_2_ld)
            + "</script>"
            "</body></html>"
        )

        mock_response_2 = MagicMock()
        mock_response_2.text = html_2
        mock_response_2.raise_for_status = MagicMock()
        mock_get.return_value = mock_response_2

        job_data_2 = GreenhouseCollector.collect(url_2)
        job_2, _, created_2 = JobProcessor.process(job_data_2)

        self.assertTrue(created_2)
        self.assertEqual(job_2.url, url_2)
        self.assertEqual(job_2.company, "Company B")

        # Assert: Two separate Job records exist
        self.assertEqual(Job.objects.count(), 2)
        self.assertNotEqual(job_1.id, job_2.id)
