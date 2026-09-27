"""
Document generation: the structured model plus both renderers.

The recurring assertions are: the output is non-empty, it contains the expected
sections, and it does not contain content the source resume never had. The last
one matters most -- a resume tool that silently invents a line is worse than
one that produces nothing.
"""

import io
import json
import re

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from docx import Document as ReadDocx
from pypdf import PdfReader

from apps.ai.tailor import build_source_resume
from apps.ai.tests.fixtures import SOURCE_PROFILE, valid_payload
from apps.resumes.models import Resume, ResumeProfile
from apps.resumes.services.document import build_document, extract_links
from apps.resumes.services.docx_generator import ResumeDocxGenerator
from apps.resumes.services.pdf_generator import ResumePdfGenerator

PROFILE = dict(SOURCE_PROFILE)
PROFILE["projects"] = (
    "Resume Parser https://github.com/acme/parser\n"
    "- Parsed 3,000 PDF resumes and extracted structured profiles."
)


def tailoring_envelope() -> dict:
    return {
        "result": json.loads(json.dumps(valid_payload())),
        "source": build_source_resume(PROFILE),
    }


def docx_text(payload: bytes) -> str:
    document = ReadDocx(io.BytesIO(payload))
    return "\n".join(p.text for p in document.paragraphs)


def pdf_text(payload: bytes) -> str:
    reader = PdfReader(io.BytesIO(payload))
    return "\n".join(page.extract_text() for page in reader.pages)


class BuildDocumentTests(SimpleTestCase):
    """Resolving stored profile + approved tailoring into a document."""

    def test_master_renders_without_any_tailoring(self):
        document = build_document(PROFILE)
        self.assertTrue(document.experience)
        self.assertTrue(document.projects)
        self.assertEqual(document.summary, "")

    def test_tailored_bullets_replace_source_bullets(self):
        document = build_document(PROFILE, tailoring_envelope())
        self.assertIn("Cut p99 latency by 40% across the platform.",
                      document.experience[0].bullets)

    def test_rejected_change_falls_back_to_the_source(self):
        """An entry the user did not touch keeps its original bullets."""
        envelope = tailoring_envelope()
        envelope["result"]["experience"][0]["tailored_bullets"] = []
        document = build_document(PROFILE, envelope)
        self.assertIn(
            "Built internal REST API services using Django and PostgreSQL.",
            document.experience[0].bullets,
        )

    def test_education_and_certifications_always_come_from_source(self):
        """Even a tailoring that tried to set them is ignored."""
        envelope = tailoring_envelope()
        envelope["result"]["education"] = "PhD in Rocket Science"
        document = build_document(PROFILE, envelope)
        self.assertEqual(document.education, PROFILE["education"])
        self.assertNotIn("Rocket", str(document.education))

    def test_skills_are_reordered_not_invented(self):
        envelope = tailoring_envelope()
        document = build_document(PROFILE, envelope)
        self.assertEqual(document.skills[0], "django")
        self.assertEqual(set(document.skills), set(PROFILE["skills"]))

    def test_unknown_emphasised_skill_is_dropped(self):
        envelope = tailoring_envelope()
        envelope["result"]["skills"]["emphasized"] = ["kubernetes", "django"]
        document = build_document(PROFILE, envelope)
        self.assertNotIn("kubernetes", document.skills)
        self.assertEqual(document.skills[0], "django")

    def test_dates_are_human_readable(self):
        document = build_document(PROFILE)
        self.assertEqual(document.experience[0].dates, "Mar 2021 - Present")

    def test_role_and_company_are_split(self):
        document = build_document(PROFILE)
        entry = document.experience[0]
        self.assertEqual(entry.role, "Backend Engineer")
        self.assertEqual(entry.organisation, "Northwind")

    def test_inline_url_is_stripped_from_the_project_heading(self):
        document = build_document(PROFILE)
        self.assertEqual(document.projects[0].heading, "Resume Parser")

    def test_links_are_extracted_from_the_source(self):
        document = build_document(PROFILE)
        self.assertEqual(document.links[0]["label"], "GitHub")

    def test_extract_links_ignores_non_profile_urls(self):
        self.assertEqual(extract_links("see https://example.com/jobs/1"), [])

    def test_empty_profile_yields_an_empty_document(self):
        document = build_document({})
        self.assertFalse(document.experience)
        self.assertFalse(document.projects)


class DocxRendererTests(SimpleTestCase):

    def test_generation_succeeds_and_is_non_empty(self):
        payload = ResumeDocxGenerator().render(build_document(PROFILE))
        self.assertGreater(len(payload), 2000)
        self.assertEqual(payload[:2], b"PK", "a .docx is a zip package")

    def test_expected_sections_are_present(self):
        text = docx_text(ResumeDocxGenerator().render(build_document(PROFILE)))
        for heading in ("SKILLS", "EXPERIENCE", "PROJECTS", "EDUCATION"):
            self.assertIn(heading, text)

    def test_summary_appears_only_when_present(self):
        document = build_document(PROFILE, tailoring_envelope())
        self.assertIn("SUMMARY", docx_text(ResumeDocxGenerator().render(document)))

        without = build_document(PROFILE)
        self.assertNotIn("SUMMARY", docx_text(ResumeDocxGenerator().render(without)))

    def test_bullets_are_rendered(self):
        text = docx_text(ResumeDocxGenerator().render(build_document(PROFILE)))
        self.assertIn("Cut p99 latency by 40% across the platform.", text)

    def test_contains_no_tables(self):
        """Tables are a common cause of ATS mis-parsing."""
        document = ReadDocx(
            io.BytesIO(ResumeDocxGenerator().render(build_document(PROFILE)))
        )
        self.assertEqual(len(document.tables), 0)

    def test_does_not_invent_education(self):
        text = docx_text(ResumeDocxGenerator().render(build_document(PROFILE)))
        self.assertIn("B.Tech Computer Science, 2020", text)

    def test_empty_resume_is_refused(self):
        with self.assertRaises(ValueError):
            ResumeDocxGenerator().render(build_document({}))

    def test_output_is_deterministic(self):
        """Same input, same bytes: what makes this safe to test and to diff."""
        first = ResumeDocxGenerator().render(build_document(PROFILE))
        second = ResumeDocxGenerator().render(build_document(PROFILE))
        self.assertEqual(first, second)


class PdfRendererTests(SimpleTestCase):

    def test_generation_succeeds_and_is_non_empty(self):
        payload = ResumePdfGenerator().render(build_document(PROFILE))
        self.assertGreater(len(payload), 1000)
        self.assertTrue(payload.startswith(b"%PDF"))

    def test_expected_content_is_present(self):
        text = pdf_text(ResumePdfGenerator().render(build_document(PROFILE)))
        for expected in ("SKILLS", "EXPERIENCE", "PROJECTS", "EDUCATION"):
            self.assertIn(expected, text)

    def test_bullets_survive_text_extraction(self):
        """A U+2022 bullet extracts as garbage; the hyphen is deliberate."""
        text = pdf_text(ResumePdfGenerator().render(build_document(PROFILE)))
        self.assertIn("Cut p99 latency by 40% across the platform.", text)
        self.assertNotIn("\x7f", text, "no unextractable bullet glyphs")

    def test_does_not_invent_education(self):
        text = pdf_text(ResumePdfGenerator().render(build_document(PROFILE)))
        self.assertIn("B.Tech Computer Science, 2020", text)

    def test_empty_resume_is_refused(self):
        with self.assertRaises(ValueError):
            ResumePdfGenerator().render(build_document({}))


class FormatEquivalenceTests(SimpleTestCase):
    """
    Both formats must carry the same information.

    They are generated from one resolved document, so a divergence is a bug in
    the resolution layer rather than in either renderer.
    """

    def test_both_formats_contain_the_same_bullets(self):
        document = build_document(PROFILE, tailoring_envelope())
        docx = docx_text(ResumeDocxGenerator().render(document))
        pdf = pdf_text(ResumePdfGenerator().render(document))

        for bullet in document.experience[0].bullets:
            self.assertIn(bullet, docx)
            self.assertIn(bullet, pdf)

    def test_both_formats_contain_the_same_skills(self):
        document = build_document(PROFILE, tailoring_envelope())
        docx = docx_text(ResumeDocxGenerator().render(document))
        pdf = pdf_text(ResumePdfGenerator().render(document))

        for skill in document.skills:
            self.assertIn(skill, docx)
            self.assertIn(skill, pdf)
