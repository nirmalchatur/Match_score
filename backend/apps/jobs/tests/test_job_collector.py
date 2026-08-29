"""
Tests for JobCollector.collect_from_url() URL integration.

Tests the pipeline:
    URL → JobFetcher.fetch(url) → JDParser.parse(html) → JobData
"""

from unittest.mock import patch, MagicMock

from django.test import TestCase
import requests

from apps.jobs.services.job_collector import JobCollector, JobData


class JobCollectorCollectFromURLTest(TestCase):
    """Test JobCollector.collect_from_url() integration."""

    def setUp(self):
        self.collector = JobCollector()
        self.html = (
            "<html>"
            "<head>"
            "<style>.hidden { display:none; }</style>"
            "<script>alert('ignore');</script>"
            "</head>"
            "<body>"
            "<h1>Python Backend Engineer</h1>"
            "<p>Requirements</p>"
            "<p>Python, Django, AWS and Docker</p>"
            "</body>"
            "</html>"
        )

    @patch("apps.jobs.services.job_collector.JDParser")
    @patch("apps.jobs.services.job_collector.JobFetcher")
    def test_collect_from_url_successfully_creates_jobdata(
        self,
        mock_fetcher,
        mock_parser,
    ):
        """collect_from_url should successfully create JobData."""

        # Mock the fetcher and parser
        mock_fetcher.fetch.return_value = self.html
        mock_parser.parse.return_value = (
            "Python Backend Engineer Requirements "
            "Python, Django, AWS and Docker"
        )

        source_data = {
            "url": "https://example.com/job/123",
            "company": "Example Corp",
            "title": "Python Backend Engineer",
            "location": "Pune",
        }

        result = self.collector.collect_from_url(source_data)

        self.assertIsInstance(result, JobData)
        self.assertEqual(
            result.url,
            "https://example.com/job/123",
        )
        self.assertEqual(result.company, "Example Corp")
        self.assertEqual(
            result.title,
            "Python Backend Engineer",
        )
        self.assertEqual(result.location, "Pune")
        self.assertIn(
            "Python Backend Engineer",
            result.description,
        )

        # Verify mocks were called
        mock_fetcher.fetch.assert_called_once_with(
            "https://example.com/job/123"
        )
        mock_parser.parse.assert_called_once_with(self.html)

    @patch("apps.jobs.services.job_collector.JDParser")
    @patch("apps.jobs.services.job_collector.JobFetcher")
    def test_collect_from_url_preserves_all_metadata(
        self,
        mock_fetcher,
        mock_parser,
    ):
        """collect_from_url should preserve url, company, title, location."""

        mock_fetcher.fetch.return_value = self.html
        mock_parser.parse.return_value = "Clean job description"

        source_data = {
            "url": "https://jobs.example.com/positions/456",
            "company": "Tech Innovations Inc",
            "title": "Senior Backend Developer",
            "location": "San Francisco, CA",
        }

        result = self.collector.collect_from_url(source_data)

        self.assertEqual(
            result.url,
            "https://jobs.example.com/positions/456",
        )
        self.assertEqual(result.company, "Tech Innovations Inc")
        self.assertEqual(
            result.title,
            "Senior Backend Developer",
        )
        self.assertEqual(result.location, "San Francisco, CA")

    @patch("apps.jobs.services.job_collector.JDParser")
    @patch("apps.jobs.services.job_collector.JobFetcher")
    def test_collect_from_url_removes_scripts_and_styles(
        self,
        mock_fetcher,
        mock_parser,
    ):
        """collect_from_url should produce clean description without scripts/styles."""

        mock_fetcher.fetch.return_value = self.html

        # Mock parser to simulate actual parsing
        def mock_parse(html):
            from apps.jobs.services.jd_parser import (
                JDParser as RealJDParser,
            )

            return RealJDParser.parse(html)

        mock_parser.parse.side_effect = mock_parse

        source_data = {
            "url": "https://example.com/job",
            "company": "Example",
            "title": "Engineer",
        }

        result = self.collector.collect_from_url(source_data)

        # Verify content is present
        self.assertIn(
            "Python Backend Engineer",
            result.description,
        )
        self.assertIn(
            "Python, Django, AWS and Docker",
            result.description,
        )

        # Verify script content is removed
        self.assertNotIn("alert", result.description)

        # Verify style content is removed
        self.assertNotIn("hidden", result.description)
        self.assertNotIn("display:none", result.description)

    @patch("apps.jobs.services.job_collector.JDParser")
    @patch("apps.jobs.services.job_collector.JobFetcher")
    def test_collect_from_url_handles_optional_location(
        self,
        mock_fetcher,
        mock_parser,
    ):
        """collect_from_url should allow missing location."""

        mock_fetcher.fetch.return_value = self.html
        mock_parser.parse.return_value = "Job description"

        source_data = {
            "url": "https://example.com/job",
            "company": "Example",
            "title": "Engineer",
            # No location provided
        }

        result = self.collector.collect_from_url(source_data)

        self.assertEqual(result.location, "")

    @patch("apps.jobs.services.job_collector.JDParser")
    @patch("apps.jobs.services.job_collector.JobFetcher")
    def test_collect_from_url_rejects_missing_url(
        self,
        mock_fetcher,
        mock_parser,
    ):
        """collect_from_url should reject missing URL."""

        source_data = {
            "company": "Example",
            "title": "Engineer",
        }

        with self.assertRaises(ValueError) as ctx:
            self.collector.collect_from_url(source_data)

        self.assertIn("url", str(ctx.exception).lower())

        # Mock should not be called
        mock_fetcher.fetch.assert_not_called()

    @patch("apps.jobs.services.job_collector.JDParser")
    @patch("apps.jobs.services.job_collector.JobFetcher")
    def test_collect_from_url_rejects_missing_company(
        self,
        mock_fetcher,
        mock_parser,
    ):
        """collect_from_url should reject missing company."""

        source_data = {
            "url": "https://example.com/job",
            "title": "Engineer",
        }

        with self.assertRaises(ValueError) as ctx:
            self.collector.collect_from_url(source_data)

        self.assertIn("company", str(ctx.exception).lower())

        # Mock should not be called
        mock_fetcher.fetch.assert_not_called()

    @patch("apps.jobs.services.job_collector.JDParser")
    @patch("apps.jobs.services.job_collector.JobFetcher")
    def test_collect_from_url_rejects_missing_title(
        self,
        mock_fetcher,
        mock_parser,
    ):
        """collect_from_url should reject missing title."""

        source_data = {
            "url": "https://example.com/job",
            "company": "Example",
        }

        with self.assertRaises(ValueError) as ctx:
            self.collector.collect_from_url(source_data)

        self.assertIn("title", str(ctx.exception).lower())

        # Mock should not be called
        mock_fetcher.fetch.assert_not_called()

    @patch("apps.jobs.services.job_collector.JDParser")
    @patch("apps.jobs.services.job_collector.JobFetcher")
    def test_collect_from_url_propagates_fetch_failure(
        self,
        mock_fetcher,
        mock_parser,
    ):
        """collect_from_url should propagate fetch errors."""

        mock_fetcher.fetch.side_effect = requests.RequestException(
            "Connection failed"
        )

        source_data = {
            "url": "https://example.com/job",
            "company": "Example",
            "title": "Engineer",
        }

        with self.assertRaises(requests.RequestException):
            self.collector.collect_from_url(source_data)

    @patch("apps.jobs.services.job_collector.JDParser")
    @patch("apps.jobs.services.job_collector.JobFetcher")
    def test_collect_from_url_propagates_parse_failure(
        self,
        mock_fetcher,
        mock_parser,
    ):
        """collect_from_url should propagate parse errors."""

        mock_fetcher.fetch.return_value = self.html
        mock_parser.parse.side_effect = ValueError(
            "No text content found in HTML"
        )

        source_data = {
            "url": "https://example.com/job",
            "company": "Example",
            "title": "Engineer",
        }

        with self.assertRaises(ValueError):
            self.collector.collect_from_url(source_data)

    @patch("apps.jobs.services.job_collector.JDParser")
    @patch("apps.jobs.services.job_collector.JobFetcher")
    def test_collect_from_url_strips_whitespace_in_metadata(
        self,
        mock_fetcher,
        mock_parser,
    ):
        """collect_from_url should strip whitespace from metadata."""

        mock_fetcher.fetch.return_value = self.html
        mock_parser.parse.return_value = "Description"

        source_data = {
            "url": "  https://example.com/job  ",
            "company": "  Example Corp  ",
            "title": "  Engineer  ",
            "location": "  Pune  ",
        }

        result = self.collector.collect_from_url(source_data)

        self.assertEqual(result.url, "https://example.com/job")
        self.assertEqual(result.company, "Example Corp")
        self.assertEqual(result.title, "Engineer")
        self.assertEqual(result.location, "Pune")


class JobCollectorCollectTest(TestCase):
    """Test that existing JobCollector.collect() still works."""

    def setUp(self):
        self.collector = JobCollector()

    def test_collect_still_works_with_clean_description(self):
        """Existing collect() method should still work."""

        source_data = {
            "url": "https://example.com/job",
            "company": "Example Corp",
            "title": "Engineer",
            "description": "Build backend services",
        }

        result = self.collector.collect(source_data)

        self.assertIsInstance(result, JobData)
        self.assertEqual(result.url, "https://example.com/job")
        self.assertEqual(result.company, "Example Corp")
        self.assertEqual(result.title, "Engineer")
        self.assertEqual(
            result.description,
            "Build backend services",
        )

    def test_collect_rejects_missing_description(self):
        """Existing collect() should still require description."""

        source_data = {
            "url": "https://example.com/job",
            "company": "Example Corp",
            "title": "Engineer",
        }

        with self.assertRaises(ValueError) as ctx:
            self.collector.collect(source_data)

        self.assertIn("description", str(ctx.exception).lower())

    def test_collect_and_collect_from_url_coexist(self):
        """Both collect() and collect_from_url() should be available."""

        # verify both methods exist
        self.assertTrue(
            hasattr(
                self.collector,
                "collect",
            )
        )
        self.assertTrue(
            hasattr(
                self.collector,
                "collect_from_url",
            )
        )

        # verify they are callable
        self.assertTrue(
            callable(
                self.collector.collect,
            )
        )
        self.assertTrue(
            callable(
                self.collector.collect_from_url,
            )
        )
