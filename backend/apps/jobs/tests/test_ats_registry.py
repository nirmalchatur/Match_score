"""
Tests for the ATS registry: which adapter handles which URL.

Detection is the part with teeth. It runs on a hostname before anything is
fetched, and the obvious suffix check (``host.endswith("greenhouse.io")``)
also matches ``greenhouse.io.evil.com`` -- an attacker-controlled host that
would then be handed to a parser which trusts the domain. So the boundary
cases are asserted rather than assumed.
"""

from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase

from apps.jobs.services import ats_registry
from apps.jobs.services.job_collector import JobData
from apps.jobs.services.sources.base import host_matches
from apps.jobs.services.sources.generic import GenericCollector
from apps.jobs.services.sources.greenhouse import GreenhouseSource
from apps.jobs.services.sources.workday import WorkdayCollector


class HostMatchingTests(SimpleTestCase):
    """The dot-boundary rule, which is the security-relevant part."""

    def test_exact_domain_matches(self):
        self.assertTrue(host_matches("greenhouse.io", "greenhouse.io"))

    def test_subdomain_matches(self):
        self.assertTrue(host_matches("acme.greenhouse.io", "greenhouse.io"))

    def test_suffix_attack_does_not_match(self):
        """The whole reason host_matches exists instead of str.endswith."""
        for host in (
            "greenhouse.io.evil.com",
            "evilgreenhouse.io",
            "not-greenhouse.io",
        ):
            self.assertFalse(
                host_matches(host, "greenhouse.io"), f"{host} must not match"
            )

    def test_trailing_dot_is_tolerated(self):
        """A fully-qualified name with a root dot is still the same host."""
        self.assertTrue(host_matches("acme.greenhouse.io.", "greenhouse.io"))

    def test_case_is_ignored(self):
        self.assertTrue(host_matches("ACME.Greenhouse.IO", "greenhouse.io"))


class DetectionTests(SimpleTestCase):
    def test_greenhouse_urls(self):
        for url in (
            "https://acme.greenhouse.io/jobs/123",
            "https://job-boards.greenhouse.io/acme/jobs/123",
        ):
            self.assertEqual(ats_registry.source_slug(url), "greenhouse", url)

    def test_workday_urls(self):
        for url in (
            "https://acme.wd1.myworkdayjobs.com/en-GB/Engineer_JR-1234",
            "https://acme.wd3.myworkdayjobs.com/en-US/Engineer_JR-9",
            "https://acme.myworkdayjobs.com/en-GB/Engineer_JR-9",
        ):
            self.assertEqual(ats_registry.source_slug(url), "workday", url)

    def test_anything_else_is_generic(self):
        for url in (
            "https://example.com/careers/1",
            "https://jobs.lever.co/acme/1234",
            "https://acme.wd1.myworkdayjobs.com.evil.com/x",
            "https://greenhouse.io.evil.com/jobs/1",
        ):
            self.assertEqual(ats_registry.source_slug(url), "generic", url)

    def test_a_url_with_no_host_is_rejected(self):
        for url in ("", "not-a-url", "ftp://example.com/x", "javascript:alert(1)"):
            with self.assertRaises(ValueError):
                ats_registry.detect(url)

    def test_the_generic_adapter_is_last(self):
        """
        Order is load-bearing and nothing else enforces it.

        GenericCollector matches every URL. If it were registered before a
        specific adapter, that adapter would become unreachable and the app
        would quietly regress to a generic scraper with no test failing.
        """
        names = [source.name for source in ats_registry.SOURCES]
        self.assertEqual(names[-1], "generic")
        self.assertLess(
            names.index("greenhouse"),
            names.index("generic"),
            "Greenhouse must be checked before the catch-all",
        )
        self.assertLess(
            names.index("workday"),
            names.index("generic"),
            "Workday must be checked before the catch-all",
        )

    def test_supported_sources_are_described_for_the_ui(self):
        listed = ats_registry.supported_sources()
        self.assertEqual([entry["name"] for entry in listed][-1], "generic")
        self.assertTrue(listed[-1]["fallback"])
        for entry in listed:
            self.assertTrue(entry["label"])

class CollectTests(SimpleTestCase):
    def test_collect_records_the_adapter_that_read_it(self):
        url = "https://acme.wd1.myworkdayjobs.com/en-GB/Engineer_JR-1"
        payload = {
            "jobPostingInfo": {
                "title": "Engineer",
                "company": "Acme",
                "location": "London",
                "jobDescription": "<p>Build things.</p>",
            }
        }
        response = Mock(status_code=200)
        response.json.return_value = payload

        with patch(
            "apps.jobs.services.sources.workday.requests.get", return_value=response
        ):
            data = ats_registry.collect(url)

        self.assertEqual(data.source, "workday")
        self.assertEqual(data.title, "Engineer")

    def test_a_greenhouse_posting_is_labelled_greenhouse(self):
        url = "https://acme.greenhouse.io/jobs/1"
        data = JobData(url=url, company="Acme", title="T", location="", description="d")
        with patch.object(GreenhouseSource, "collect", return_value=data):
            self.assertEqual(ats_registry.collect(url).source, "greenhouse")

    def test_an_adapter_that_forgets_to_set_the_source_is_still_labelled(self):
        """
        The registry normalises, so a new adapter cannot ship a blank badge.

        Written for the next person adding Lever: they do not have to remember
        to set ``source``, and they cannot forget to.
        """
        url = "https://example.com/careers/1"
        data = JobData(url=url, company="Acme", title="T", location="", description="d")
        self.assertEqual(data.source, "", "precondition: this JobData has no source")

        with patch.object(GenericCollector, "collect", return_value=data):
            self.assertEqual(ats_registry.collect(url).source, "generic")


class WorkdayUrlTests(SimpleTestCase):
    def test_cxs_url_is_derived_from_the_posting(self):
        self.assertEqual(
            WorkdayCollector.cxs_url(
                "https://acme.wd1.myworkdayjobs.com/en-GB/Engineer_JR-1234"
            ),
            "https://acme.wd1.myworkdayjobs.com/wday/cxs/acme/en-GB/Engineer_JR-1234",
        )

    def test_a_company_landing_page_is_refused(self):
        """Pointing the adapter at a careers index cannot produce a posting."""
        with self.assertRaises(ValueError):
            WorkdayCollector.cxs_url("https://acme.wd1.myworkdayjobs.com/")

    def test_a_non_workday_url_is_refused(self):
        with self.assertRaises(ValueError):
            WorkdayCollector.cxs_url("https://example.com/jobs/1")

    def test_a_private_tenant_says_so_rather_than_pretending(self):
        url = "https://acme.wd1.myworkdayjobs.com/en-GB/Engineer_JR-1"
        response = Mock(status_code=403)
        with patch(
            "apps.jobs.services.sources.workday.requests.get", return_value=response
        ):
            with self.assertRaises(ValueError) as ctx:
                WorkdayCollector().collect(url)
        self.assertIn("browser", str(ctx.exception))

    def test_a_waf_challenge_page_is_reported_as_such(self):
        """
        A challenge page is HTML where JSON was expected.

        Without this the code raises a bare JSONDecodeError, which tells the
        user nothing about what went wrong.
        """
        url = "https://acme.wd1.myworkdayjobs.com/en-GB/Engineer_JR-1"
        response = Mock(status_code=200)
        response.json.side_effect = ValueError("not json")
        with patch(
            "apps.jobs.services.sources.workday.requests.get", return_value=response
        ):
            with self.assertRaises(ValueError) as ctx:
                WorkdayCollector().collect(url)
        self.assertIn("bot check", str(ctx.exception))

    def test_a_search_page_is_not_mistaken_for_a_job(self):
        url = "https://acme.wd1.myworkdayjobs.com/en-GB/Engineer_JR-1"
        response = Mock(status_code=200)
        response.json.return_value = {"searchResults": []}
        with patch(
            "apps.jobs.services.sources.workday.requests.get", return_value=response
        ):
            with self.assertRaises(ValueError):
                WorkdayCollector().collect(url)

    def test_a_timeout_is_reported_as_a_fetch_failure(self):
        url = "https://acme.wd1.myworkdayjobs.com/en-GB/Engineer_JR-1"
        with patch(
            "apps.jobs.services.sources.workday.requests.get",
            side_effect=requests.Timeout(),
        ):
            with self.assertRaises(requests.RequestException):
                WorkdayCollector().collect(url)

    def test_list_items_survive_as_separate_lines(self):
        """
        Description text feeds the skill extractor.

        Collapsing <li> items into one run-on line turns "Docker, Kubernetes,
        Terraform" into a single unrecognised token and quietly degrades the
        match score, so the line structure is asserted directly.
        """
        text = WorkdayCollector._html_to_text(
            "<ul><li>Docker</li><li>Kubernetes</li><li>Terraform</li></ul>"
        )
        self.assertEqual(text.splitlines(), ["Docker", "Kubernetes", "Terraform"])


class GreenhouseAdapterTests(SimpleTestCase):
    def test_it_reuses_the_strict_collector_url_check(self):
        source = GreenhouseSource()
        self.assertTrue(source.matches("https://acme.greenhouse.io/jobs/1"))
        self.assertFalse(source.matches("https://greenhouse.io/jobs/1"))
        self.assertFalse(source.matches("https://greenhouse.io.evil.com/jobs/1"))
