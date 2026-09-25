"""
Tests for GreenhouseCollector job board adapter.

Comprehensive test coverage for:
- URL validation (strict greenhouse.io domain checking)
- JSON-LD parsing (dict, list, multiple objects, @type variations)
- Location extraction (dict, list, PostalAddress)
- Description normalization (HTML to plain text)
- Company extraction (hiringOrganization preference, hostname fallback)
- Error handling (missing fields, malformed responses, HTTP errors)
- Fallback to HTML parsing
- Real Greenhouse HTML structure with current CSS classes
"""

from unittest.mock import patch, MagicMock
import json

from django.test import TestCase
import requests

from apps.jobs.services.sources.greenhouse import GreenhouseCollector
from apps.jobs.services.job_collector import JobData


class GreenhouseCollectorURLValidationTest(TestCase):
    """Test strict URL validation for official Greenhouse.io domains."""

    def test_A_valid_greenhouse_url(self):
        """A. Valid greenhouse.io URL with company subdomain."""
        with patch(
            "apps.jobs.services.sources.greenhouse.requests.get"
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.text = (
                "<html><body>"
                "<script type='application/ld+json'>"
                '{"@type": "JobPosting", "title": "Engineer", '
                '"description": "Build things", '
                '"hiringOrganization": {"name": "Acme"}}'
                "</script></body></html>"
            )
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = GreenhouseCollector.collect(
                "https://acme.greenhouse.io/jobs/123"
            )

            self.assertIsInstance(result, JobData)
            self.assertEqual(result.title, "Engineer")

    def test_B_reject_bare_greenhouse_io(self):
        """B. Reject bare greenhouse.io (no subdomain)."""
        with self.assertRaises(ValueError) as ctx:
            GreenhouseCollector.collect(
                "https://greenhouse.io/jobs/123"
            )

        self.assertIn("greenhouse", str(ctx.exception).lower())

    def test_C_reject_www_greenhouse_io(self):
        """C. Reject www.greenhouse.io (reserved subdomain)."""
        with self.assertRaises(ValueError) as ctx:
            GreenhouseCollector.collect(
                "https://www.greenhouse.io/jobs/123"
            )

        self.assertIn("greenhouse", str(ctx.exception).lower())

    def test_D_reject_greenhouse_io_evil_com(self):
        """D. Reject greenhouse.io.evil.com (domain suffix attack)."""
        with self.assertRaises(ValueError) as ctx:
            GreenhouseCollector.collect(
                "https://greenhouse.io.evil.com/jobs/123"
            )

        self.assertIn("greenhouse", str(ctx.exception).lower())

    def test_E_reject_non_greenhouse_url(self):
        """E. Reject non-Greenhouse URL."""
        with self.assertRaises(ValueError) as ctx:
            GreenhouseCollector.collect(
                "https://example.com/jobs/123"
            )

        self.assertIn("greenhouse", str(ctx.exception).lower())

    def test_reject_evilgreenhouse_io(self):
        """Reject unrelated domains ending in greenhouse.io-like pattern."""
        with self.assertRaises(ValueError):
            GreenhouseCollector.collect(
                "https://evilgreenhouse.io/jobs/123"
            )

    def test_reject_multiple_subdomains(self):
        """Reject URLs with multiple subdomains (not [company].greenhouse.io)."""
        with self.assertRaises(ValueError):
            GreenhouseCollector.collect(
                "https://jobs.acme.greenhouse.io/jobs/123"
            )


class GreenhouseCollectorJSONLDTest(TestCase):
    """Test JSON-LD extraction with various formats."""

    def test_F_json_ld_job_posting_dict(self):
        """F. JSON-LD JobPosting as dictionary."""
        with patch(
            "apps.jobs.services.sources.greenhouse.requests.get"
        ) as mock_get:
            json_ld = {
                "@type": "JobPosting",
                "title": "Senior Engineer",
                "description": "Build scalable systems",
                "hiringOrganization": {"name": "TechCorp"},
            }

            mock_response = MagicMock()
            mock_response.text = (
                "<html><body>"
                "<script type='application/ld+json'>"
                + json.dumps(json_ld)
                + "</script></body></html>"
            )
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = GreenhouseCollector.collect(
                "https://techcorp.greenhouse.io/jobs/123"
            )

            self.assertEqual(result.title, "Senior Engineer")
            self.assertIn("Build scalable", result.description)

    def test_G_json_ld_job_posting_list(self):
        """G. JSON-LD JobPosting in a list."""
        with patch(
            "apps.jobs.services.sources.greenhouse.requests.get"
        ) as mock_get:
            json_ld_list = [
                {
                    "@type": "Organization",
                    "name": "TechCorp",
                },
                {
                    "@type": "JobPosting",
                    "title": "Senior Engineer",
                    "description": "Build scalable systems",
                },
            ]

            mock_response = MagicMock()
            mock_response.text = (
                "<html><body>"
                "<script type='application/ld+json'>"
                + json.dumps(json_ld_list)
                + "</script></body></html>"
            )
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = GreenhouseCollector.collect(
                "https://techcorp.greenhouse.io/jobs/123"
            )

            self.assertEqual(result.title, "Senior Engineer")

    def test_H_json_ld_multiple_objects(self):
        """H. JSON-LD with multiple script tags."""
        with patch(
            "apps.jobs.services.sources.greenhouse.requests.get"
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.text = (
                "<html><body>"
                "<script type='application/ld+json'>"
                '{"@type": "Organization"}'
                "</script>"
                "<script type='application/ld+json'>"
                '{"@type": "JobPosting", "title": "Engineer", '
                '"description": "Build things"}'
                "</script>"
                "</body></html>"
            )
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = GreenhouseCollector.collect(
                "https://techcorp.greenhouse.io/jobs/123"
            )

            self.assertEqual(result.title, "Engineer")

    def test_I_json_ld_type_as_list(self):
        """I. JSON-LD @type as list ["JobPosting", "Thing"]."""
        with patch(
            "apps.jobs.services.sources.greenhouse.requests.get"
        ) as mock_get:
            json_ld = {
                "@type": ["JobPosting", "Thing"],
                "title": "Senior Engineer",
                "description": "Build scalable systems",
            }

            mock_response = MagicMock()
            mock_response.text = (
                "<html><body>"
                "<script type='application/ld+json'>"
                + json.dumps(json_ld)
                + "</script></body></html>"
            )
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = GreenhouseCollector.collect(
                "https://techcorp.greenhouse.io/jobs/123"
            )

            self.assertEqual(result.title, "Senior Engineer")


class GreenhouseCollectorCompanyExtractionTest(TestCase):
    """Test company extraction from various sources."""

    def test_J_company_from_hiring_organization(self):
        """J. Company extracted from hiringOrganization."""
        with patch(
            "apps.jobs.services.sources.greenhouse.requests.get"
        ) as mock_get:
            json_ld = {
                "@type": "JobPosting",
                "title": "Engineer",
                "description": "Build things",
                "hiringOrganization": {
                    "@type": "Organization",
                    "name": "Acme Corporation",
                },
            }

            mock_response = MagicMock()
            mock_response.text = (
                "<html><body>"
                "<script type='application/ld+json'>"
                + json.dumps(json_ld)
                + "</script></body></html>"
            )
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = GreenhouseCollector.collect(
                "https://ignored.greenhouse.io/jobs/123"
            )

            self.assertEqual(result.company, "Acme Corporation")

    def test_K_company_fallback_from_hostname(self):
        """K. Company extracted from hostname when JSON-LD missing."""
        with patch(
            "apps.jobs.services.sources.greenhouse.requests.get"
        ) as mock_get:
            json_ld = {
                "@type": "JobPosting",
                "title": "Engineer",
                "description": "Build things",
                # No hiringOrganization
            }

            mock_response = MagicMock()
            mock_response.text = (
                "<html><body>"
                "<script type='application/ld+json'>"
                + json.dumps(json_ld)
                + "</script></body></html>"
            )
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = GreenhouseCollector.collect(
                "https://acme-corp.greenhouse.io/jobs/123"
            )

            self.assertEqual(result.company, "Acme Corp")


class GreenhouseCollectorLocationExtractionTest(TestCase):
    """Test location extraction from JSON-LD."""

    def test_L_location_extraction(self):
        """L. Location extracted from jobLocation."""
        with patch(
            "apps.jobs.services.sources.greenhouse.requests.get"
        ) as mock_get:
            json_ld = {
                "@type": "JobPosting",
                "title": "Engineer",
                "description": "Build things",
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

            mock_response = MagicMock()
            mock_response.text = (
                "<html><body>"
                "<script type='application/ld+json'>"
                + json.dumps(json_ld)
                + "</script></body></html>"
            )
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = GreenhouseCollector.collect(
                "https://acme.greenhouse.io/jobs/123"
            )

            self.assertIn("San Francisco", result.location)
            self.assertIn("California", result.location)

    def test_M_location_missing_returns_empty_string(self):
        """M. Missing location returns empty string."""
        with patch(
            "apps.jobs.services.sources.greenhouse.requests.get"
        ) as mock_get:
            json_ld = {
                "@type": "JobPosting",
                "title": "Remote Engineer",
                "description": "Work from anywhere",
                # No jobLocation for remote role
            }

            mock_response = MagicMock()
            mock_response.text = (
                "<html><body>"
                "<script type='application/ld+json'>"
                + json.dumps(json_ld)
                + "</script></body></html>"
            )
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = GreenhouseCollector.collect(
                "https://acme.greenhouse.io/jobs/123"
            )

            self.assertEqual(result.location, "")

    def test_location_with_partial_data(self):
        """Location with only city (no state/country)."""
        with patch(
            "apps.jobs.services.sources.greenhouse.requests.get"
        ) as mock_get:
            json_ld = {
                "@type": "JobPosting",
                "title": "Engineer",
                "description": "Build things",
                "jobLocation": {
                    "@type": "Place",
                    "address": {
                        "@type": "PostalAddress",
                        "addressLocality": "New York",
                    },
                },
            }

            mock_response = MagicMock()
            mock_response.text = (
                "<html><body>"
                "<script type='application/ld+json'>"
                + json.dumps(json_ld)
                + "</script></body></html>"
            )
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = GreenhouseCollector.collect(
                "https://acme.greenhouse.io/jobs/123"
            )

            self.assertEqual(result.location, "New York")


class GreenhouseCollectorDescriptionNormalizationTest(TestCase):
    """Test description normalization and HTML cleaning."""

    def test_N_html_description_converted_to_clean_text(self):
        """N. HTML description normalized to clean text."""
        with patch(
            "apps.jobs.services.sources.greenhouse.requests.get"
        ) as mock_get:
            json_ld = {
                "@type": "JobPosting",
                "title": "Engineer",
                "description": (
                    "<p>Build <strong>scalable</strong> systems.</p>"
                    "<ul><li>Python</li><li>Django</li></ul>"
                ),
            }

            mock_response = MagicMock()
            mock_response.text = (
                "<html><body>"
                "<script type='application/ld+json'>"
                + json.dumps(json_ld)
                + "</script></body></html>"
            )
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = GreenhouseCollector.collect(
                "https://acme.greenhouse.io/jobs/123"
            )

            # Should not contain HTML tags
            self.assertNotIn("<p>", result.description)
            self.assertNotIn("<strong>", result.description)
            self.assertNotIn("<ul>", result.description)
            # Should contain text content
            self.assertIn("scalable", result.description)
            self.assertIn("Python", result.description)
            self.assertIn("Django", result.description)

    def test_plain_text_description_unchanged(self):
        """Plain text description without HTML remains unchanged."""
        with patch(
            "apps.jobs.services.sources.greenhouse.requests.get"
        ) as mock_get:
            plain_description = (
                "Build scalable systems using Python and Django."
            )

            json_ld = {
                "@type": "JobPosting",
                "title": "Engineer",
                "description": plain_description,
            }

            mock_response = MagicMock()
            mock_response.text = (
                "<html><body>"
                "<script type='application/ld+json'>"
                + json.dumps(json_ld)
                + "</script></body></html>"
            )
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = GreenhouseCollector.collect(
                "https://acme.greenhouse.io/jobs/123"
            )

            self.assertEqual(result.description, plain_description)


class GreenhouseCollectorMissingFieldsTest(TestCase):
    """Test handling of missing required fields."""

    def test_O_missing_title(self):
        """O. Missing job title raises error."""
        with patch(
            "apps.jobs.services.sources.greenhouse.requests.get"
        ) as mock_get:
            json_ld = {
                "@type": "JobPosting",
                # Missing title
                "description": "Build things",
            }

            mock_response = MagicMock()
            mock_response.text = (
                "<html><body>"
                "<script type='application/ld+json'>"
                + json.dumps(json_ld)
                + "</script></body></html>"
            )
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            with self.assertRaises(ValueError):
                GreenhouseCollector.collect(
                    "https://acme.greenhouse.io/jobs/123"
                )

    def test_P_missing_description(self):
        """P. Missing job description raises error."""
        with patch(
            "apps.jobs.services.sources.greenhouse.requests.get"
        ) as mock_get:
            json_ld = {
                "@type": "JobPosting",
                "title": "Engineer",
                # Missing description
            }

            mock_response = MagicMock()
            mock_response.text = (
                "<html><body>"
                "<script type='application/ld+json'>"
                + json.dumps(json_ld)
                + "</script></body></html>"
            )
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            with self.assertRaises(ValueError):
                GreenhouseCollector.collect(
                    "https://acme.greenhouse.io/jobs/123"
                )


class GreenhouseCollectorFallbackTest(TestCase):
    """Test fallback to HTML parsing."""

    def test_Q_invalid_json_ld_fallback_to_html(self):
        """Q. Invalid JSON-LD falls back to HTML parsing."""
        with patch(
            "apps.jobs.services.sources.greenhouse.requests.get"
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.text = (
                "<html><body>"
                "<script type='application/ld+json'>"
                '{"@type": "JobPosting", "title": "Engineer"}'
                # Missing description in JSON-LD
                "</script>"
                "<h1>Senior Engineer</h1>"
                "<div class='job__location'>Remote</div>"
                "<div class='job__description'>"
                "Build scalable systems with Python"
                "</div>"
                "</body></html>"
            )
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = GreenhouseCollector.collect(
                "https://acme.greenhouse.io/jobs/123"
            )

            # Should fallback to HTML and use h1 title
            self.assertIn("Engineer", result.title)

    def test_missing_location_does_not_fail_html_fallback(self):
        """Missing explicit location nodes should still parse valid jobs."""
        with patch(
            "apps.jobs.services.sources.greenhouse.requests.get"
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.text = """
            <html>
                <body>
                    <div class="job-post-container">
                        <div class="job__header">
                            <div class="job__title">
                                <h1>Senior Product Engineer</h1>
                            </div>
                        </div>
                        <div class="job__description">
                            <p>Build product experiences and matching systems.</p>
                        </div>
                    </div>
                </body>
            </html>
            """
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = GreenhouseCollector.collect(
                "https://acme.greenhouse.io/jobs/123"
            )

            self.assertEqual(result.title, "Senior Product Engineer")
            self.assertEqual(result.location, "")
            self.assertIn("Build product experiences", result.description)

    def test_real_greenhouse_html_structure(self):
        """Test the current Greenhouse job-board HTML structure."""
        with patch(
            "apps.jobs.services.sources.greenhouse.requests.get"
        ) as mock_get:

            mock_response = MagicMock()

            mock_response.text = """
            <html>
                <body>
                    <div class="job-post-container">
                        <div class="job__header">
                            <div class="job__title">
                                <h1>Software Engineer (Contract, Argentina)</h1>
                                Argentina
                            </div>
                            <div class="job__location">
                                Argentina
                            </div>
                        </div>

                        <div class="job__description">
                            <p>
                                Our mission at Greenhouse is to make hiring
                                work for everyone.
                            </p>
                            <p>
                                You will build web applications and matching
                                systems.
                            </p>
                        </div>

                        <div class="application--container">
                            Apply for this job
                        </div>
                    </div>
                </body>
            </html>
            """

            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            url = (
                "https://job-boards.greenhouse.io/"
                "greenhouse/jobs/8148418?gh_jid=8148418"
            )

            result = GreenhouseCollector.collect(url)

            self.assertIsInstance(result, JobData)

            self.assertEqual(
                result.title,
                "Software Engineer (Contract, Argentina)",
            )

            self.assertEqual(
                result.location,
                "Argentina",
            )

            self.assertIn(
                "Our mission at Greenhouse",
                result.description,
            )
            self.assertIn(
                "web applications",
                result.description,
            )
            self.assertIn(
                "matching",
                result.description,
            )
            self.assertIn(
                "systems",
                result.description,
            )

            self.assertNotIn(
                "Back to jobs",
                result.description,
            )

            self.assertNotIn(
                "Apply for this job",
                result.description,
            )


class GreenhouseCollectorErrorHandlingTest(TestCase):
    """Test error handling."""

    def test_R_http_failure(self):
        """R. HTTP failures are handled properly."""
        with patch(
            "apps.jobs.services.sources.greenhouse.requests.get"
        ) as mock_get:
            mock_get.side_effect = requests.ConnectionError(
                "Connection failed"
            )

            with self.assertRaises(requests.RequestException):
                GreenhouseCollector.collect(
                    "https://acme.greenhouse.io/jobs/123"
                )

    def test_timeout_error(self):
        """Timeout errors are handled properly."""
        with patch(
            "apps.jobs.services.sources.greenhouse.requests.get"
        ) as mock_get:
            mock_get.side_effect = requests.Timeout(
                "Connection timed out"
            )

            with self.assertRaises(requests.RequestException):
                GreenhouseCollector.collect(
                    "https://acme.greenhouse.io/jobs/123"
                )

    def test_http_404_error(self):
        """404 errors are handled properly."""
        with patch(
            "apps.jobs.services.sources.greenhouse.requests.get"
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock(
                side_effect=requests.HTTPError("404 Not Found")
            )
            mock_get.return_value = mock_response

            with self.assertRaises(requests.RequestException):
                GreenhouseCollector.collect(
                    "https://acme.greenhouse.io/jobs/123"
                )


class GreenhouseCollectorIntegrationTest(TestCase):
    """Integration tests."""

    def test_full_pipeline(self):
        """Complete pipeline from URL to JobData."""
        with patch(
            "apps.jobs.services.sources.greenhouse.requests.get"
        ) as mock_get:
            json_ld = {
                "@type": "JobPosting",
                "title": "Senior Backend Engineer",
                "description": (
                    "<p>Build <strong>scalable</strong> "
                    "backend systems.</p>"
                ),
                "hiringOrganization": {
                    "name": "TechCorp Inc",
                },
                "jobLocation": {
                    "@type": "Place",
                    "address": {
                        "@type": "PostalAddress",
                        "addressLocality": "San Francisco",
                        "addressRegion": "California",
                    },
                },
            }

            mock_response = MagicMock()
            mock_response.text = (
                "<html><body>"
                "<script type='application/ld+json'>"
                + json.dumps(json_ld)
                + "</script></body></html>"
            )
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = GreenhouseCollector.collect(
                "https://techcorp.greenhouse.io/jobs/senior-backend-engineer"
            )

            self.assertIsInstance(result, JobData)
            self.assertEqual(
                result.url,
                "https://techcorp.greenhouse.io/jobs/senior-backend-engineer",
            )
            self.assertEqual(result.title, "Senior Backend Engineer")
            self.assertEqual(result.company, "TechCorp Inc")
            self.assertIn("San Francisco", result.location)
            self.assertIn("scalable", result.description)
            self.assertNotIn("<strong>", result.description)

    def test_company_name_normalization(self):
        """Company names with hyphens are normalized."""
        with patch(
            "apps.jobs.services.sources.greenhouse.requests.get"
        ) as mock_get:
            json_ld = {
                "@type": "JobPosting",
                "title": "Engineer",
                "description": "Build things",
            }

            mock_response = MagicMock()
            mock_response.text = (
                "<html><body>"
                "<script type='application/ld+json'>"
                + json.dumps(json_ld)
                + "</script></body></html>"
            )
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = GreenhouseCollector.collect(
                "https://tech-innovators-inc.greenhouse.io/jobs/123"
            )

            self.assertEqual(result.company, "Tech Innovators Inc")

    def test_url_preserved_in_result(self):
        """URL is preserved in the result."""
        with patch(
            "apps.jobs.services.sources.greenhouse.requests.get"
        ) as mock_get:
            json_ld = {
                "@type": "JobPosting",
                "title": "Engineer",
                "description": "Build things",
            }

            mock_response = MagicMock()
            mock_response.text = (
                "<html><body>"
                "<script type='application/ld+json'>"
                + json.dumps(json_ld)
                + "</script></body></html>"
            )
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            url = "https://example.greenhouse.io/jobs/abc-123-xyz"

            result = GreenhouseCollector.collect(url)

            self.assertEqual(result.url, url)