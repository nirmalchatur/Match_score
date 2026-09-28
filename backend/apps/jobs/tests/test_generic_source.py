"""
Tests for the generic adapter: JSON-LD first, HTML as a fallback.

The fallback will always return *something*, and that is the danger. Pointed
at a careers index or a cookie wall it yields a plausible title and a
meaningless description, and the match score is computed from that
description -- so the result looks authoritative while being wrong. These
tests pin the behaviour that makes the difference visible: JSON-LD wins when
present, and the fallback refuses rather than inventing.
"""

import json
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.jobs.services.sources.generic import GenericCollector


def page(body: str, head: str = "") -> str:
    return f"<html><head>{head}</head><body>{body}</body></html>"


def ld(obj) -> str:
    return (
        '<script type="application/ld+json">'
        + json.dumps(obj)
        + "</script>"
    )


class JsonLdTests(SimpleTestCase):
    def collect(self, html: str):
        response = Mock(status_code=200, text=html)
        with patch(
            "apps.jobs.services.sources.generic.requests.get", return_value=response
        ):
            return GenericCollector().collect("https://example.com/jobs/1")

    def test_a_jobposting_block_is_read(self):
        html = page(
            ld(
                {
                    "@type": "JobPosting",
                    "title": "Backend Engineer",
                    "description": "<p>Build services.</p>",
                    "hiringOrganization": {"name": "Acme"},
                    "jobLocation": {
                        "address": {"addressLocality": "Bengaluru"}
                    },
                }
            )
        )
        data = self.collect(html)
        self.assertEqual(data.title, "Backend Engineer")
        self.assertEqual(data.company, "Acme")
        self.assertEqual(data.location, "Bengaluru")
        self.assertEqual(data.source, "generic")

    def test_hiringorganization_may_be_a_bare_string(self):
        """Seen in the wild often enough that a dict-only reader loses jobs."""
        html = page(
            ld(
                {
                    "@type": "JobPosting",
                    "title": "Engineer",
                    "description": "Build things that matter here.",
                    "hiringOrganization": "Acme Inc",
                }
            )
        )
        self.assertEqual(self.collect(html).company, "Acme Inc")

    def test_a_graph_wrapped_posting_is_found(self):
        html = page(
            ld(
                {
                    "@context": "https://schema.org",
                    "@graph": [
                        {"@type": "WebSite", "name": "Acme"},
                        {
                            "@type": "JobPosting",
                            "title": "Engineer",
                            "description": "Build things that matter here.",
                        },
                    ],
                }
            )
        )
        self.assertEqual(self.collect(html).title, "Engineer")

    def test_an_array_of_postings_takes_the_first_job(self):
        html = page(
            ld(
                [
                    {
                        "@type": "JobPosting",
                        "title": "First",
                        "description": "Build things that matter here.",
                    },
                    {
                        "@type": "JobPosting",
                        "title": "Second",
                        "description": "Build other things here.",
                    },
                ]
            )
        )
        self.assertEqual(self.collect(html).title, "First")

    def test_a_posting_with_no_description_is_not_used(self):
        """
        A JobPosting with no description would be scored against nothing.

        Falling through to HTML here is correct: a real description is on the
        page, just not in the structured block.
        """
        html = page(
            ld({"@type": "JobPosting", "title": "Engineer", "description": ""}),
            head="",
        ) + "<main>" + ("<p>Real description text. " * 30) + "</p></main>"
        data = self.collect(html)
        self.assertIn("Real description", data.description)

    def test_malformed_json_ld_falls_through_instead_of_raising(self):
        """One broken block should not cost us the whole page."""
        html = page(
            '<script type="application/ld+json">{ not json </script>'
            + "<main>" + ("<p>Real description text. " * 30) + "</p></main>"
        )
        self.assertIn("Real description", self.collect(html).description)


class HtmlFallbackTests(SimpleTestCase):
    def collect(self, html: str):
        response = Mock(status_code=200, text=html)
        with patch(
            "apps.jobs.services.sources.generic.requests.get", return_value=response
        ):
            return GenericCollector().collect("https://example.com/jobs/1")

    def test_open_graph_title_beats_the_page_title(self):
        """<title> is often "<title> - Acme Careers"; og:title is the role."""
        html = page(
            "<main>" + ("<p>Description body text. " * 40) + "</main>",
            head='<meta property="og:title" content="Senior Engineer">'
            '<title>Senior Engineer - Acme Careers</title>',
        )
        self.assertEqual(self.collect(html).title, "Senior Engineer")

    def test_the_main_element_is_preferred_over_page_chrome(self):
        """A careers index mentions every job; the posting mentions one."""
        html = page(
            "<nav>Apply Now Contact Us Cookie Policy</nav>"
            "<main>" + ("<p>The actual job description. " * 40) + "</main>"
        )
        description = self.collect(html).description
        self.assertIn("actual job description", description)
        self.assertLess(len(description), 2000)

    def test_a_page_with_no_usable_content_fails_rather_than_guessing(self):
        """
        The important one.

        Returning an empty description would produce a job with a real-looking
        title and a 0% match score, which reads as "you are a poor fit" when
        the truth is "we could not read the page". Failing says so.
        """
        with self.assertRaises(ValueError) as ctx:
            self.collect(page("<div></div>"))
        self.assertIn("job description", str(ctx.exception))

    def test_company_falls_back_to_the_hostname(self):
        html = page(
            "<main>" + ("<p>Description body text. " * 40) + "</main>",
            head='<title>Engineer</title>',
        )
        self.assertEqual(self.collect(html).company, "example.com")

    def test_www_is_stripped_from_the_fallback_company(self):
        response = Mock(status_code=200)
        html = page(
            "<main>" + ("<p>Description body text. " * 40) + "</main>",
            head="<title>Engineer</title>",
        )
        response.text = html
        with patch(
            "apps.jobs.services.sources.generic.requests.get", return_value=response
        ):
            data = GenericCollector().collect("https://www.example.com/jobs/1")
        self.assertEqual(data.company, "example.com")

    def test_list_items_survive_as_separate_lines(self):
        """Skill extraction reads this; a run-on line becomes one unknown token."""
        html = page(
            "<main><ul>"
            "<li>Docker</li><li>Kubernetes</li><li>Terraform</li>"
            "</ul>" + ("<p>Filler sentence to pass the length check. " * 20)
            + "</main>"
        )
        description = self.collect(html).description
        for item in ("Docker", "Kubernetes", "Terraform"):
            self.assertIn(item, description)
        self.assertNotIn("Docker Kubernetes", description)

    def test_scripts_are_dropped_from_the_description(self):
        """Otherwise navigation JSON becomes part of the analysed job text."""
        html = page(
            "<main>" + ("<p>Real description. " * 40) + "</main>"
            + "<script>var tracking = ['Docker','Kubernetes'];</script>"
        )
        self.assertNotIn("tracking", self.collect(html).description)

    def test_a_url_with_no_scheme_is_refused_before_any_request(self):
        with patch("apps.jobs.services.sources.generic.requests.get") as fetch:
            with self.assertRaises(ValueError):
                GenericCollector().collect("example.com/jobs/1")
        fetch.assert_not_called()
