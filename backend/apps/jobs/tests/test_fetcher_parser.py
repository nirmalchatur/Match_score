"""
Tests for JobFetcher and JDParser integration.

Tests the new pipeline:
    URL → JobFetcher → HTML → JDParser → clean text → JobCollector → JobData
"""

from unittest.mock import patch, MagicMock

from django.test import TestCase
import requests

from apps.jobs.services.collector import JobFetcher
from apps.jobs.services.jd_parser import JDParser
from apps.jobs.services.job_collector import JobCollector, JobData


class JobFetcherTest(TestCase):
    """Test JobFetcher URL validation and HTTP fetching."""

    def test_fetcher_rejects_empty_url(self):
        """JobFetcher should reject empty URLs."""
        with self.assertRaises(ValueError) as ctx:
            JobFetcher.fetch("")

        self.assertIn("empty", str(ctx.exception).lower())

    def test_fetcher_rejects_none_url(self):
        """JobFetcher should reject None URLs."""
        with self.assertRaises(ValueError):
            JobFetcher.fetch(None)

    def test_fetcher_rejects_url_without_scheme(self):
        """JobFetcher should reject URLs without http:// or https://."""
        with self.assertRaises(ValueError) as ctx:
            JobFetcher.fetch("example.com")

        self.assertIn("http", str(ctx.exception).lower())

    def test_fetcher_rejects_url_with_invalid_scheme(self):
        """JobFetcher should reject URLs with non-HTTP schemes."""
        with self.assertRaises(ValueError) as ctx:
            JobFetcher.fetch("ftp://example.com")

        self.assertIn("http", str(ctx.exception).lower())

    def test_fetcher_rejects_url_without_domain(self):
        """JobFetcher should reject URLs without domain."""
        with self.assertRaises(ValueError) as ctx:
            JobFetcher.fetch("https://")

        self.assertIn("domain", str(ctx.exception).lower())

    @patch("apps.jobs.services.collector.requests.get")
    def test_fetcher_successfully_fetches_url(self, mock_get):
        """JobFetcher should successfully fetch a valid URL."""
        html = "<html><body>Test content</body></html>"
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = JobFetcher.fetch("https://example.com")

        self.assertEqual(result, html)
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        self.assertIn("https://example.com", call_args[0])

    @patch("apps.jobs.services.collector.requests.get")
    def test_fetcher_includes_user_agent(self, mock_get):
        """JobFetcher should include User-Agent header."""
        mock_response = MagicMock()
        mock_response.text = "<html></html>"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        JobFetcher.fetch("https://example.com")

        call_kwargs = mock_get.call_args[1]
        self.assertIn("headers", call_kwargs)
        self.assertIn("User-Agent", call_kwargs["headers"])

    @patch("apps.jobs.services.collector.requests.get")
    def test_fetcher_sets_timeout(self, mock_get):
        """JobFetcher should set request timeout."""
        mock_response = MagicMock()
        mock_response.text = "<html></html>"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        JobFetcher.fetch("https://example.com")

        call_kwargs = mock_get.call_args[1]
        self.assertIn("timeout", call_kwargs)
        self.assertEqual(
            call_kwargs["timeout"],
            JobFetcher.TIMEOUT_SECONDS,
        )

    @patch("apps.jobs.services.collector.requests.get")
    def test_fetcher_raises_on_timeout(self, mock_get):
        """JobFetcher should raise on timeout."""
        mock_get.side_effect = requests.Timeout(
            "Connection timed out"
        )

        with self.assertRaises(requests.RequestException):
            JobFetcher.fetch("https://example.com")

    @patch("apps.jobs.services.collector.requests.get")
    def test_fetcher_raises_on_connection_error(self, mock_get):
        """JobFetcher should raise on connection error."""
        mock_get.side_effect = requests.ConnectionError(
            "Connection failed"
        )

        with self.assertRaises(requests.RequestException):
            JobFetcher.fetch("https://example.com")

    @patch("apps.jobs.services.collector.requests.get")
    def test_fetcher_raises_on_http_error(self, mock_get):
        """JobFetcher should raise on HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status = MagicMock(
            side_effect=requests.HTTPError("Not found")
        )
        mock_get.return_value = mock_response

        with self.assertRaises(requests.RequestException):
            JobFetcher.fetch("https://example.com")


class JDParserTest(TestCase):
    """Test JDParser HTML to text conversion."""

    def test_parser_rejects_empty_html(self):
        """JDParser should reject empty HTML."""
        with self.assertRaises(ValueError) as ctx:
            JDParser.parse("")

        self.assertIn("empty", str(ctx.exception).lower())

    def test_parser_rejects_none_html(self):
        """JDParser should reject None HTML."""
        with self.assertRaises(ValueError):
            JDParser.parse(None)

    def test_parser_converts_html_to_text(self):
        """JDParser should extract text from HTML."""
        html = (
            "<html><body>"
            "<h1>Job Title</h1>"
            "<p>Requirements: Python, Django</p>"
            "</body></html>"
        )

        result = JDParser.parse(html)

        self.assertIn("Job Title", result)
        self.assertIn("Python", result)
        self.assertIn("Django", result)

    def test_parser_removes_script_tags(self):
        """JDParser should remove script tags."""
        html = (
            "<html><body>"
            "<p>Job content</p>"
            "<script>var x = 1;</script>"
            "</body></html>"
        )

        result = JDParser.parse(html)

        self.assertIn("Job content", result)
        self.assertNotIn("var x", result)
        self.assertNotIn("script", result.lower())

    def test_parser_removes_style_tags(self):
        """JDParser should remove style tags."""
        html = (
            "<html><body>"
            "<p>Job content</p>"
            "<style>body { color: red; }</style>"
            "</body></html>"
        )

        result = JDParser.parse(html)

        self.assertIn("Job content", result)
        self.assertNotIn("color", result)

    def test_parser_removes_noscript_tags(self):
        """JDParser should remove noscript tags."""
        html = (
            "<html><body>"
            "<p>Job content</p>"
            "<noscript>JavaScript disabled</noscript>"
            "</body></html>"
        )

        result = JDParser.parse(html)

        self.assertIn("Job content", result)
        self.assertNotIn("JavaScript disabled", result)

    def test_parser_removes_svg_tags(self):
        """JDParser should remove SVG tags."""
        html = (
            "<html><body>"
            "<p>Job content</p>"
            "<svg><circle r='5'/></svg>"
            "</body></html>"
        )

        result = JDParser.parse(html)

        self.assertIn("Job content", result)
        self.assertNotIn("circle", result)

    def test_parser_normalizes_whitespace(self):
        """JDParser should normalize multiple spaces."""
        html = (
            "<html><body>"
            "Requirements:\n\n"
            "  -  Python\n"
            "  -  Django\n"
            "</body></html>"
        )

        result = JDParser.parse(html)

        # Should have normalized spacing
        self.assertIn("Python", result)
        self.assertIn("Django", result)

    def test_parser_rejects_html_with_no_text(self):
        """JDParser should reject HTML with no content."""
        html = (
            "<html><body>"
            "<script>var x = 1;</script>"
            "<style>body { color: red; }</style>"
            "</body></html>"
        )

        with self.assertRaises(ValueError) as ctx:
            JDParser.parse(html)

        self.assertIn("text", str(ctx.exception).lower())


class JobCollectorTest(TestCase):
    """Test JobCollector data validation."""

    def test_collector_rejects_missing_url(self):
        """JobCollector should reject missing URL."""
        data = {
            "company": "Acme",
            "title": "Engineer",
            "description": "Build things",
        }

        collector = JobCollector()

        with self.assertRaises(ValueError) as ctx:
            collector.collect(data)

        self.assertIn("url", str(ctx.exception).lower())

    def test_collector_rejects_missing_company(self):
        """JobCollector should reject missing company."""
        data = {
            "url": "https://example.com",
            "title": "Engineer",
            "description": "Build things",
        }

        collector = JobCollector()

        with self.assertRaises(ValueError) as ctx:
            collector.collect(data)

        self.assertIn("company", str(ctx.exception).lower())

    def test_collector_rejects_missing_title(self):
        """JobCollector should reject missing title."""
        data = {
            "url": "https://example.com",
            "company": "Acme",
            "description": "Build things",
        }

        collector = JobCollector()

        with self.assertRaises(ValueError) as ctx:
            collector.collect(data)

        self.assertIn("title", str(ctx.exception).lower())

    def test_collector_rejects_missing_description(self):
        """JobCollector should reject missing description."""
        data = {
            "url": "https://example.com",
            "company": "Acme",
            "title": "Engineer",
        }

        collector = JobCollector()

        with self.assertRaises(ValueError) as ctx:
            collector.collect(data)

        self.assertIn("description", str(ctx.exception).lower())

    def test_collector_accepts_valid_data(self):
        """JobCollector should accept valid data."""
        data = {
            "url": "https://example.com/job/1",
            "company": "Acme Corp",
            "title": "Senior Engineer",
            "location": "San Francisco, CA",
            "description": (
                "Requirements: Python, Django, AWS"
            ),
        }

        collector = JobCollector()
        result = collector.collect(data)

        self.assertIsInstance(result, JobData)
        self.assertEqual(result.url, data["url"])
        self.assertEqual(result.company, data["company"])
        self.assertEqual(result.title, data["title"])
        self.assertEqual(result.location, data["location"])
        self.assertEqual(result.description, data["description"])

    def test_collector_strips_whitespace(self):
        """JobCollector should strip whitespace from fields."""
        data = {
            "url": "  https://example.com/job/1  ",
            "company": "  Acme Corp  ",
            "title": "  Engineer  ",
            "description": "  Build things  ",
        }

        collector = JobCollector()
        result = collector.collect(data)

        self.assertEqual(result.url, "https://example.com/job/1")
        self.assertEqual(result.company, "Acme Corp")
        self.assertEqual(result.title, "Engineer")
        self.assertEqual(result.description, "Build things")

    def test_collector_allows_optional_location(self):
        """JobCollector should allow missing location."""
        data = {
            "url": "https://example.com/job/1",
            "company": "Acme Corp",
            "title": "Engineer",
            "description": "Build things",
        }

        collector = JobCollector()
        result = collector.collect(data)

        self.assertEqual(result.location, "")


class IntegrationTest(TestCase):
    """Test the full pipeline: HTML → Text → JobData."""

    @patch("apps.jobs.services.collector.requests.get")
    def test_full_pipeline_html_to_jobdata(self, mock_get):
        """Test full pipeline: fetch → parse → collect."""
        # Mock the HTTP response
        html = (
            "<html><body>"
            "<h1>Python Backend Engineer</h1>"
            "<p>Requirements: 2+ years Python, Django, AWS</p>"
            "<p>Location: San Francisco</p>"
            "<script>var x = 1;</script>"
            "</body></html>"
        )

        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        # Step 1: Fetch HTML
        fetched_html = JobFetcher.fetch("https://example.com/job")

        self.assertIn("Python Backend Engineer", fetched_html)

        # Step 2: Parse HTML to text
        clean_text = JDParser.parse(fetched_html)

        self.assertIn("Python Backend Engineer", clean_text)
        self.assertIn("Requirements", clean_text)
        self.assertNotIn("script", clean_text.lower())

        # Step 3: Create JobData
        job_data = {
            "url": "https://example.com/job",
            "company": "Acme Corp",
            "title": "Python Backend Engineer",
            "location": "San Francisco",
            "description": clean_text,
        }

        collector = JobCollector()
        result = collector.collect(job_data)

        self.assertIsInstance(result, JobData)
        self.assertEqual(result.company, "Acme Corp")
        self.assertIn("Python", result.description)
