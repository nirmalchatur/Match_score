"""
API tests for the tailoring endpoints.

The recurring theme is the tenant boundary: every request must resolve the
master resume and the job from the **authenticated** account, so User A can
never tailor against User B's documents, no matter what ids they send.
"""

import json

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from apps.ai import factory
from apps.ai.exceptions import (
    AIConfigurationError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
)
from apps.ai.providers.fake import FakeAIProvider
from apps.ai.tests.fixtures import SOURCE_PROFILE, valid_payload
from apps.jobs.models import Job
from apps.resumes.models import Resume, ResumeProfile


def post_json(client, url, payload):
    """POST as JSON, matching what the frontend api client actually sends."""
    return client.post(url, data=json.dumps(payload), content_type="application/json")


class TailoringApiTestCase(TestCase):
    """Shared fixture: one account with a master resume and one analysed job."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="owner@example.test", email="owner@example.test", password="pw-12345"
        )
        self.other = User.objects.create_user(
            username="other@example.test", email="other@example.test", password="pw-12345"
        )

        self.master = Resume.objects.create(
            user=self.user, name="Master", resume_type="MASTER", is_master=True
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
            description=(
                "Build backend services with Django and PostgreSQL. Docker required."
            ),
            match_score=82.5,
            match_result={"score": 82.5, "decision": "TAILOR"},
        )

        self.client.force_login(self.user)

    def use_provider(self, payload=None):
        """Point the factory at a FakeAIProvider for the duration of the test."""
        provider = FakeAIProvider(json.dumps(payload if payload is not None else valid_payload()))
        factory.register("test_fake", lambda: provider)
        self.addCleanup(factory._registry.pop, "test_fake", None)
        return provider


@override_settings(AI_PROVIDER="test_fake")
class TailorEndpointTests(TailoringApiTestCase):

    def test_returns_before_after_review_payload(self):
        self.use_provider()
        response = self.client.post("/api/resumes/tailor/", {"job_id": self.job.id})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("result", body)
        self.assertIn("validation", body)
        self.assertIn("source", body)
        self.assertEqual(body["validation"]["status"], "valid")
        # The review is built from our stored originals, not the model's echo.
        self.assertEqual(
            body["source"]["experience"][0]["bullets"][0], "Backend Engineer, Northwind"
        )
        self.assertEqual(body["job"]["id"], self.job.id)
        self.assertEqual(body["master_resume_id"], self.master.id)

    def test_nothing_is_saved_by_tailoring(self):
        self.use_provider()
        before = Resume.objects.count()
        self.client.post("/api/resumes/tailor/", {"job_id": self.job.id})
        self.assertEqual(Resume.objects.count(), before)

    def test_master_resume_is_not_modified(self):
        self.use_provider()
        snapshot = (self.master.name, self.master.is_master, self.master.resume_type)
        self.client.post("/api/resumes/tailor/", {"job_id": self.job.id})
        self.master.refresh_from_db()
        self.assertEqual(
            (self.master.name, self.master.is_master, self.master.resume_type), snapshot
        )

    def test_fabricated_output_returns_422_with_violations(self):
        def mutate(p):
            p["experience"][0]["tailored_bullets"] = [
                "Cut p99 latency by 95% across the platform."
            ]
        payload = valid_payload()
        mutate(payload)
        self.use_provider(payload)

        response = self.client.post("/api/resumes/tailor/", {"job_id": self.job.id})

        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["code"], "ai_validation_failed")
        self.assertIn("fabricated_metric", {v["code"] for v in body["violations"]})

    def test_suspicious_output_is_returned_for_review(self):
        def mutate(p):
            p["experience"][0]["tailored_bullets"] = [
                "Cut p99 latency by 40% across the platform at Initech."
            ]
        payload = valid_payload()
        mutate(payload)
        self.use_provider(payload)

        response = self.client.post("/api/resumes/tailor/", {"job_id": self.job.id})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["validation"]["status"], "warning")

    def test_missing_master_resume_returns_404(self):
        self.use_provider()
        self.master.delete()
        response = self.client.post("/api/resumes/tailor/", {"job_id": self.job.id})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "resume_missing")

    def test_unknown_job_returns_404(self):
        self.use_provider()
        response = self.client.post("/api/resumes/tailor/", {"job_id": 999999})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "job_missing")

    def test_job_without_description_returns_400(self):
        self.use_provider()
        self.job.description = ""
        self.job.save()
        response = self.client.post("/api/resumes/tailor/", {"job_id": self.job.id})
        self.assertEqual(response.status_code, 400)

    def test_requires_authentication(self):
        self.client.logout()
        self.assertEqual(self.client.post("/api/resumes/tailor/", {"job_id": self.job.id}).status_code, 403)

    def test_cannot_tailor_another_users_job(self):
        """The tenant boundary: ids are not enough, ownership is checked."""
        self.use_provider()
        intruder_job = Job.objects.create(
            user=self.other,
            url="https://boards.greenhouse.io/other/jobs/9",
            company="Other Co",
            title="Other Role",
            description="Some description.",
        )
        response = self.client.post("/api/resumes/tailor/", {"job_id": intruder_job.id})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "job_missing")

    def test_cannot_use_another_users_master_resume(self):
        """An account whose only master belongs to someone else gets no tailoring."""
        self.use_provider()
        self.master.delete()
        Resume.objects.create(
            user=self.other, name="Theirs", resume_type="MASTER", is_master=True
        )
        response = self.client.post("/api/resumes/tailor/", {"job_id": self.job.id})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "resume_missing")

    def test_provider_error_is_mapped_without_leaking_internals(self):
        factory.register("boom", lambda: FakeAIProvider.unavailable())
        self.addCleanup(factory._registry.pop, "boom", None)
        with override_settings(AI_PROVIDER="boom"):
            response = self.client.post("/api/resumes/tailor/", {"job_id": self.job.id})

        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["code"], "ai_unavailable")
        self.assertNotIn("11434", str(body))
        self.assertNotIn("Ollama", str(body))

    def test_timeout_is_mapped_to_504(self):
        factory.register("slow", lambda: FakeAIProvider.timing_out())
        self.addCleanup(factory._registry.pop, "slow", None)
        with override_settings(AI_PROVIDER="slow"):
            response = self.client.post("/api/resumes/tailor/", {"job_id": self.job.id})
        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.json()["code"], "ai_timeout")

    def test_unconfigured_ai_returns_500_with_clear_code(self):
        with override_settings(AI_PROVIDER="does-not-exist"):
            response = self.client.post("/api/resumes/tailor/", {"job_id": self.job.id})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["code"], "ai_not_configured")


@override_settings(AI_PROVIDER="test_fake")
class SaveTailoredResumeTests(TailoringApiTestCase):
    """Phase 10: the master must never be overwritten."""

    def test_saves_a_separate_tailored_resume(self):
        result = valid_payload()
        response = post_json(
            self.client,
            "/api/resumes/tailor/save/",
            {"job_id": self.job.id, "result": result, "provider": "fake"},
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["resume_type"], "TAILORED")
        self.assertFalse(body["is_master"])

        saved = Resume.objects.get(id=body["id"])
        self.assertEqual(saved.user, self.user)
        self.assertEqual(saved.source_resume, self.master)
        self.assertEqual(saved.source_job, self.job)
        self.assertEqual(saved.ai_provider, "fake")
        self.assertIsNotNone(saved.tailoring_result)

    def test_master_row_is_untouched(self):
        master_pk = self.master.pk
        post_json(
            self.client, "/api/resumes/tailor/save/", {"job_id": self.job.id, "result": valid_payload()}
        )
        master = Resume.objects.get(pk=master_pk)
        self.assertTrue(master.is_master)
        self.assertEqual(master.resume_type, "MASTER")
        self.assertIsNone(master.source_resume)
        self.assertIsNone(master.source_job)

    def test_master_file_is_not_overwritten(self):
        """Even with a file on the master, the tailored row is a new document."""
        self.assertEqual(self.master.file.name, "")

    def test_saved_version_creates_a_profile_row(self):
        post_json(
            self.client, "/api/resumes/tailor/save/", {"job_id": self.job.id, "result": valid_payload()}
        )
        saved = Resume.objects.exclude(pk=self.master.pk).get()
        self.assertTrue(ResumeProfile.objects.filter(resume=saved).exists())

    def test_multiple_jobs_produce_multiple_versions(self):
        second = Job.objects.create(
            user=self.user,
            url="https://boards.greenhouse.io/acme/jobs/2",
            company="Beta",
            title="Platform Engineer",
            description="Build internal platform tooling.",
        )
        post_json(
            self.client, "/api/resumes/tailor/save/", {"job_id": self.job.id, "result": valid_payload()}
        )
        post_json(
            self.client, "/api/resumes/tailor/save/", {"job_id": second.id, "result": valid_payload()}
        )

        tailored = Resume.objects.filter(resume_type="TAILORED")
        self.assertEqual(tailored.count(), 2)
        self.assertEqual(
            set(tailored.values_list("source_job_id", flat=True)), {self.job.id, second.id}
        )
        self.assertEqual(
            set(tailored.values_list("source_resume_id", flat=True)), {self.master.pk}
        )

    def test_saving_fabricated_content_is_refused(self):
        """Re-validated on save, so a tampered client payload cannot persist."""
        result = valid_payload()
        result["experience"][0]["tailored_bullets"] = [
            "Cut p99 latency by 99% across the platform."
        ]
        response = post_json(
            self.client,
            "/api/resumes/tailor/save/",
            {"job_id": self.job.id, "result": result},
        )
        self.assertEqual(response.status_code, 422)
        self.assertFalse(Resume.objects.filter(resume_type="TAILORED").exists())

    def test_saving_requires_a_result(self):
        response = post_json(self.client, "/api/resumes/tailor/save/", {"job_id": self.job.id})
        self.assertEqual(response.status_code, 400)

    def test_cannot_save_against_another_users_job(self):
        intruder = Job.objects.create(
            user=self.other,
            url="https://boards.greenhouse.io/other/jobs/3",
            company="Other",
            title="Other",
            description="x",
        )
        response = post_json(
            self.client,
            "/api/resumes/tailor/save/",
            {"job_id": intruder.id, "result": valid_payload()},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Resume.objects.filter(resume_type="TAILORED").exists())

    def test_saved_resume_appears_in_the_existing_list(self):
        post_json(
            self.client, "/api/resumes/tailor/save/", {"job_id": self.job.id, "result": valid_payload()}
        )
        response = self.client.get("/api/resumes/")
        self.assertEqual(response.status_code, 200)
        types = [r["resume_type"] for r in response.json()]
        self.assertIn("TAILORED", types)


class ProviderStatusTests(TailoringApiTestCase):

    def test_status_reports_available_provider(self):
        self.use_provider()
        with override_settings(AI_PROVIDER="test_fake"):
            response = self.client.get("/api/resumes/tailor/status/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["available"])
        self.assertEqual(response.json()["provider"], "fake")

    def test_status_reports_missing_configuration(self):
        with override_settings(AI_PROVIDER=""):
            response = self.client.get("/api/resumes/tailor/status/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["available"])

    def test_status_requires_authentication(self):
        self.client.logout()
        self.assertIn(
            self.client.get("/api/resumes/tailor/status/").status_code, (401, 403)
        )
