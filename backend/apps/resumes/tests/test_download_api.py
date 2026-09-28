"""
Download endpoint tests, with the tenant boundary as the recurring theme.

The rule under test: a document is only ever produced for a resume the caller
owns. Everything else -- unauthenticated, another account's resume, an unknown
id, a bad format -- must be refused without leaking whether the id exists.
"""

import json

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from apps.ai import factory
from apps.ai.providers.fake import FakeAIProvider
from apps.ai.tests.fixtures import SOURCE_PROFILE, valid_payload
from apps.jobs.models import Job
from apps.resumes.models import Resume, ResumeProfile


def post_json(client, url, payload):
    return client.post(url, data=json.dumps(payload), content_type="application/json")


class DownloadApiTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="owner@example.test", email="owner@example.test", password="pw-12345"
        )
        self.other = User.objects.create_user(
            username="other@example.test", email="other@example.test", password="pw-12345"
        )

        self.master = Resume.objects.create(
            user=self.user, name="Master Resume", resume_type="MASTER", is_master=True
        )
        ResumeProfile.objects.create(
            resume=self.master,
            skills=SOURCE_PROFILE["skills"],
            experience=SOURCE_PROFILE["experience"],
            education=SOURCE_PROFILE["education"],
            projects=SOURCE_PROFILE["projects"],
            certifications=SOURCE_PROFILE["certifications"],
        )

        self.job = Job.objects.create(
            user=self.user,
            url="https://boards.greenhouse.io/acme/jobs/1",
            company="Acme",
            title="Senior Backend Engineer",
            description="Build backend services with Django and PostgreSQL.",
        )

        self.client.force_login(self.user)

    def save_tailored(self, result=None):
        """Create a tailored version through the real save endpoint."""
        provider = FakeAIProvider(json.dumps(valid_payload()))
        factory.register("dl_fake", lambda: provider)
        self.addCleanup(factory._registry.pop, "dl_fake", None)

        with override_settings(AI_PROVIDER="dl_fake"):
            response = post_json(
                self.client,
                "/api/resumes/tailor/",
                {"job_id": self.job.id},
            )
            assert response.status_code == 200, response.content
            body = response.json()

            saved = post_json(
                self.client,
                "/api/resumes/tailor/save/",
                {"job_id": self.job.id, "result": result or body["result"],
                 "provider": "fake"},
            )
            assert saved.status_code == 201, saved.content
            return saved.json()


class MasterDownloadTests(DownloadApiTestCase):

    def test_docx_download_succeeds(self):
        response = self.client.get("/api/resumes/%d/download/docx/" % self.master.id)
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.content), 2000)

    def test_pdf_download_succeeds(self):
        response = self.client.get("/api/resumes/%d/download/pdf/" % self.master.id)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_content_types_are_correct(self):
        docx = self.client.get("/api/resumes/%d/download/docx/" % self.master.id)
        pdf = self.client.get("/api/resumes/%d/download/pdf/" % self.master.id)

        self.assertIn(
            "wordprocessingml.document", docx["Content-Type"]
        )
        self.assertEqual(pdf["Content-Type"], "application/pdf")

    def test_content_disposition_is_an_attachment(self):
        response = self.client.get("/api/resumes/%d/download/docx/" % self.master.id)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("Master Resume.docx", response["Content-Disposition"])

    def test_no_filesystem_path_is_disclosed(self):
        response = self.client.get("/api/resumes/%d/download/pdf/" % self.master.id)
        disposition = response["Content-Disposition"]
        self.assertNotIn("/", disposition.replace("/filename", ""))
        self.assertNotIn("media", disposition.lower())

    def test_response_is_not_cacheable(self):
        response = self.client.get("/api/resumes/%d/download/pdf/" % self.master.id)
        self.assertIn("no-store", response["Cache-Control"])

    def test_master_download_does_not_modify_the_master(self):
        before = (self.master.name, self.master.is_master, self.master.updated_at)
        self.client.get("/api/resumes/%d/download/docx/" % self.master.id)
        self.master.refresh_from_db()
        self.assertEqual(
            (self.master.name, self.master.is_master, self.master.updated_at), before
        )


class TailoredDownloadTests(DownloadApiTestCase):

    def test_tailored_resume_downloads_in_both_formats(self):
        saved = self.save_tailored()
        for fmt, magic in (("docx", b"PK"), ("pdf", b"%PDF")):
            response = self.client.get("/api/resumes/%d/download/%s/" % (saved["id"], fmt))
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.content.startswith(magic))

    def test_tailored_document_contains_the_approved_bullets(self):
        saved = self.save_tailored()
        response = self.client.get("/api/resumes/%d/download/docx/" % saved["id"])
        from apps.resumes.tests.test_documents import docx_text
        text = docx_text(response.content)
        self.assertIn("Cut p99 latency by 40% across the platform.", text)

    def test_saved_resume_records_full_provenance(self):
        saved = self.save_tailored()
        resume = Resume.objects.get(id=saved["id"])
        self.assertEqual(resume.source_resume_id, self.master.id)
        self.assertEqual(resume.source_job_id, self.job.id)
        self.assertEqual(resume.ai_provider, "fake")
        self.assertIsNotNone(resume.created_at)
        self.assertIsNotNone(resume.updated_at)
        # The source view is re-derived server-side, so a saved version can
        # always explain its own before/after review.
        self.assertIn("source", resume.tailoring_result)
        self.assertIn("validation", resume.tailoring_result)

    def test_master_is_untouched_by_save_then_download(self):
        saved = self.save_tailored()
        self.client.get("/api/resumes/%d/download/pdf/" % saved["id"])
        self.master.refresh_from_db()
        self.assertTrue(self.master.is_master)
        self.assertEqual(self.master.resume_type, "MASTER")
        self.assertIsNone(self.master.source_resume_id)

    def test_download_filename_is_clean_and_derived_from_the_resume(self):
        saved = self.save_tailored()
        response = self.client.get("/api/resumes/%d/download/docx/" % saved["id"])
        disposition = response["Content-Disposition"]
        # Company + role, no leaked master name or stray punctuation.
        self.assertIn("Acme - Senior Backend Engineer.docx", disposition)
        self.assertNotIn("(", disposition)

    def test_filename_is_sanitised_against_header_injection(self):
        nasty = Resume.objects.create(
            user=self.user,
            name='Evil"; drop table resumes; --',
            resume_type="TAILORED",
        )
        ResumeProfile.objects.create(
            resume=nasty, skills=SOURCE_PROFILE["skills"],
            experience=SOURCE_PROFILE["experience"],
        )
        response = self.client.get("/api/resumes/%d/download/pdf/" % nasty.id)
        self.assertEqual(response.status_code, 200)
        disposition = response["Content-Disposition"]
        self.assertNotIn('"', disposition[len('attachment; filename="'):-1])
        self.assertNotIn(";", disposition.split("filename=")[1])

    def test_master_download_filename_uses_its_own_name(self):
        response = self.client.get("/api/resumes/%d/download/pdf/" % self.master.id)
        self.assertIn("Master Resume.pdf", response["Content-Disposition"])

    def test_user_edited_bullets_are_what_get_rendered(self):
        """The stored result is the user-approved one, not the raw AI output."""
        edited = valid_payload()
        edited["experience"][0]["tailored_bullets"] = [
            "Cut p99 latency by 40% across the platform (user-edited wording)."
        ]
        saved = self.save_tailored(result=edited)

        from apps.resumes.tests.test_documents import docx_text
        response = self.client.get("/api/resumes/%d/download/docx/" % saved["id"])
        text = docx_text(response.content)
        self.assertIn("user-edited wording", text)
        self.assertNotIn("Built internal REST API services.", text)

    def test_edit_that_fabricates_is_refused_on_save(self):
        """User edits are still validated: the backend is not a rubber stamp."""
        edited = valid_payload()
        edited["experience"][0]["tailored_bullets"] = [
            "Cut p99 latency by 99% across the platform."
        ]
        with override_settings(AI_PROVIDER="dl_fake"):
            provider = FakeAIProvider(json.dumps(valid_payload()))
            factory.register("dl_fake2", lambda: provider)
            self.addCleanup(factory._registry.pop, "dl_fake2", None)

            response = post_json(
                self.client,
                "/api/resumes/tailor/save/",
                {"job_id": self.job.id, "result": edited},
            )
        self.assertEqual(response.status_code, 422)
        self.assertFalse(Resume.objects.filter(resume_type="TAILORED").exists())

    def test_edit_with_malformed_structure_is_refused(self):
        with override_settings(AI_PROVIDER="dl_fake"):
            response = post_json(
                self.client,
                "/api/resumes/tailor/save/",
                {"job_id": self.job.id, "result": "not-an-object"},
            )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Resume.objects.filter(resume_type="TAILORED").exists())

    def test_edit_emptying_every_entry_falls_back_to_source(self):
        """A rejected-everything result must not blank the resume."""
        emptied = valid_payload()
        emptied["experience"] = []
        emptied["projects"] = []
        saved = self.save_tailored(result=emptied)

        from apps.resumes.tests.test_documents import docx_text
        response = self.client.get("/api/resumes/%d/download/docx/" % saved["id"])
        text = docx_text(response.content)
        self.assertIn("Backend Engineer", text)
        self.assertIn("Cut p99 latency by 40% across the platform.", text)


class DownloadSecurityTests(DownloadApiTestCase):

    def test_unauthenticated_request_is_rejected(self):
        self.client.logout()
        for fmt in ("docx", "pdf"):
            response = self.client.get(
                "/api/resumes/%d/download/%s/" % (self.master.id, fmt)
            )
            self.assertIn(response.status_code, (401, 403))

    def test_cannot_download_another_users_resume(self):
        """404, not 403: the response must not confirm the id exists."""
        self.client.logout()
        self.client.force_login(self.other)

        for fmt in ("docx", "pdf"):
            response = self.client.get(
                "/api/resumes/%d/download/%s/" % (self.master.id, fmt)
            )
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["code"], "resume_missing")

    def test_cannot_download_another_users_tailored_resume(self):
        saved = self.save_tailored()
        tailored_id = saved["id"]

        self.client.logout()
        self.client.force_login(self.other)

        response = self.client.get("/api/resumes/%d/download/docx/" % tailored_id)
        self.assertEqual(response.status_code, 404)

    def test_missing_resume_returns_404(self):
        response = self.client.get("/api/resumes/999999/download/docx/")
        self.assertEqual(response.status_code, 404)

    def test_unknown_format_is_refused(self):
        response = self.client.get("/api/resumes/%d/download/rtf/" % self.master.id)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "unsupported_format")

    def test_empty_resume_reports_a_render_failure(self):
        """A resume with no parseable content must fail loudly, not serve a blank file."""
        empty = Resume.objects.create(
            user=self.user, name="Empty", resume_type="TAILORED"
        )
        ResumeProfile.objects.create(resume=empty, skills=[], experience={})
        response = self.client.get("/api/resumes/%d/download/docx/" % empty.id)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "render_failed")


class DownloadListingTests(DownloadApiTestCase):

    def test_list_endpoint_advertises_document_availability(self):
        self.save_tailored()
        response = self.client.get("/api/resumes/")
        self.assertEqual(response.status_code, 200)
        for item in response.json():
            self.assertTrue(item["has_documents"])

    def test_list_endpoint_exposes_provenance(self):
        saved = self.save_tailored()
        response = self.client.get("/api/resumes/")
        tailored = next(r for r in response.json() if r["id"] == saved["id"])

        self.assertEqual(tailored["source_resume"], self.master.id)
        self.assertEqual(tailored["source_job"], self.job.id)
        self.assertEqual(tailored["ai_provider"], "fake")
        self.assertEqual(tailored["tailoring_summary"], "valid")
        self.assertIn("updated_at", tailored)

    def test_list_never_returns_another_users_resumes(self):
        self.save_tailored()
        self.client.logout()
        self.client.force_login(self.other)
        self.assertEqual(self.client.get("/api/resumes/").json(), [])


class ResumeFileEndpointTests(TestCase):
    """
    GET /api/resumes/<pk>/file/ -- the original upload.

    This is what the "Open" button points at. It exists because linking
    MEDIA_URL was broken twice over, and the third problem it fixes is the
    important one: a static route would make every resume readable by anyone
    who guessed the URL.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="owner@example.test", email="owner@example.test", password="pw-12345"
        )
        self.other = User.objects.create_user(
            username="other@example.test", email="other@example.test", password="pw-12345"
        )

    def make_resume(self, user, name="cv.pdf"):
        from django.core.files.uploadedfile import SimpleUploadedFile

        upload = SimpleUploadedFile(name, b"%PDF-1.4 fake bytes for testing", content_type="application/pdf")
        return Resume.objects.create(
            user=user, name="CV", resume_type="MASTER", is_master=True, file=upload
        )

    def test_the_owner_can_open_their_own_upload(self):
        resume = self.make_resume(self.user)
        self.client.force_login(self.user)
        response = self.client.get(f"/api/resumes/{resume.id}/file/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("inline", response["Content-Disposition"])
        b"".join(response.streaming_content)

    def test_another_account_gets_404_not_403(self):
        """
        403 would confirm the id exists.

        Every other read in this project answers 404 for a record owned by
        someone else, and this endpoint must not become the exception.
        """
        resume = self.make_resume(self.other)
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.get(f"/api/resumes/{resume.id}/file/").status_code, 404
        )

    def test_anonymous_visitors_are_rejected(self):
        resume = self.make_resume(self.user)
        self.client.logout()
        self.assertIn(
            self.client.get(f"/api/resumes/{resume.id}/file/").status_code, (401, 403)
        )

    def test_a_resume_without_an_upload_is_404(self):
        """Tailored resumes are generated, so they have no file to open."""
        resume = Resume.objects.create(
            user=self.user, name="Tailored", resume_type="TAILORED"
        )
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.get(f"/api/resumes/{resume.id}/file/").status_code, 404
        )

    def test_a_missing_file_on_disk_is_reported_not_500(self):
        """
        A deploy that lost its media volume leaves rows pointing nowhere.

        That is a real, recoverable condition for the user, so it gets a 410
        with an instruction rather than a stack trace.
        """
        resume = self.make_resume(self.user)
        resume.file.storage.delete(resume.file.name)
        self.client.force_login(self.user)
        response = self.client.get(f"/api/resumes/{resume.id}/file/")
        self.assertEqual(response.status_code, 410)
        self.assertEqual(response.json()["code"], "file_missing")

    def test_the_response_is_not_cacheable(self):
        """A personal document must not sit in a shared proxy's cache."""
        resume = self.make_resume(self.user)
        self.client.force_login(self.user)
        response = self.client.get(f"/api/resumes/{resume.id}/file/")
        self.assertIn("no-store", response["Cache-Control"])

    def test_the_route_does_not_leak_a_filesystem_path(self):
        resume = self.make_resume(self.user)
        self.client.force_login(self.user)
        response = self.client.get(f"/api/resumes/{resume.id}/file/")
        b"".join(response.streaming_content)
        # Only the bare filename may appear, never MEDIA_ROOT.
        self.assertNotIn("media\\", response["Content-Disposition"])
        self.assertNotIn("media/", response["Content-Disposition"])
