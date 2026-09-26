"""
Application tracker tests.

The recurring theme is the tenant boundary. Every mutation and every read is
exercised twice where it matters: once as the owner, once as a second account,
asserting the second account cannot see, change or delete the first's row -- and
that the response does not even confirm the id exists.
"""

import json

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.applications.dashboard import dashboard_stats
from apps.applications.models import Application
from apps.jobs.models import Job
from apps.resumes.models import Resume, ResumeProfile


def post_json(client, url, payload):
    return client.post(url, data=json.dumps(payload), content_type="application/json")


def patch_json(client, url, payload):
    return client.patch(url, data=json.dumps(payload), content_type="application/json")


class ApplicationTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="owner@example.test", email="owner@example.test", password="pw-12345"
        )
        self.other = User.objects.create_user(
            username="other@example.test", email="other@example.test", password="pw-12345"
        )

        self.job = Job.objects.create(
            user=self.user,
            url="https://boards.greenhouse.io/acme/jobs/1",
            company="Acme",
            title="Senior Backend Engineer",
            description="Build backend services with Django and PostgreSQL.",
            match_score=86.0,
        )
        self.other_job = Job.objects.create(
            user=self.other,
            url="https://boards.greenhouse.io/other/jobs/9",
            company="Other Co",
            title="Other Role",
            description="Something else entirely.",
        )

        self.resume = Resume.objects.create(
            user=self.user, name="Master", resume_type="MASTER", is_master=True
        )
        ResumeProfile.objects.create(resume=self.resume, skills=["python"], experience={})

        self.client.force_login(self.user)


class CreateTests(ApplicationTestCase):

    def test_create_defaults_to_saved(self):
        response = post_json(self.client, "/api/applications/", {"job": self.job.id})
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "SAVED")
        self.assertIsNone(body["applied_at"])

    def test_create_derives_owner_from_the_session(self):
        """A user_id in the body must be ignored, never honoured."""
        response = post_json(
            self.client,
            "/api/applications/",
            {"job": self.job.id, "user": self.other.id},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Application.objects.get(id=response.json()["id"]).user, self.user)

    def test_create_cannot_attach_another_users_job(self):
        response = post_json(
            self.client, "/api/applications/", {"job": self.other_job.id}
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Application.objects.exists())

    def test_create_cannot_attach_another_users_resume(self):
        foreign = Resume.objects.create(
            user=self.other, name="Theirs", resume_type="MASTER", is_master=True
        )
        response = post_json(
            self.client,
            "/api/applications/",
            {"job": self.job.id, "tailored_resume": foreign.id},
        )
        self.assertEqual(response.status_code, 400)

    def test_create_can_attach_own_tailored_resume(self):
        tailored = Resume.objects.create(
            user=self.user, name="Acme", resume_type="TAILORED",
            source_resume=self.resume, source_job=self.job,
        )
        response = post_json(
            self.client,
            "/api/applications/",
            {"job": self.job.id, "tailored_resume": tailored.id},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["tailored_resume"], tailored.id)

    def test_duplicate_application_for_same_job_is_rejected(self):
        post_json(self.client, "/api/applications/", {"job": self.job.id})
        response = post_json(self.client, "/api/applications/", {"job": self.job.id})
        self.assertEqual(response.status_code, 400)

    def test_missing_job_is_rejected(self):
        self.assertEqual(
            post_json(self.client, "/api/applications/", {}).status_code, 400
        )

    def test_response_includes_nested_job_details(self):
        body = post_json(
            self.client, "/api/applications/", {"job": self.job.id}
        ).json()
        self.assertEqual(body["job_detail"]["company"], "Acme")
        self.assertEqual(body["job_detail"]["match_score"], 86.0)


class ListTests(ApplicationTestCase):

    def setUp(self):
        super().setUp()
        self.application = Application.objects.create(
            user=self.user, job=self.job, status="INTERVIEW"
        )

    def test_lists_only_own_applications(self):
        Application.objects.create(user=self.other, job=self.other_job)

        response = self.client.get("/api/applications/")
        self.assertEqual(response.status_code, 200)
        ids = [row["id"] for row in response.json()]
        self.assertIn(self.application.id, ids)
        self.assertEqual(len(ids), 1, "another account's application leaked")

    def test_filter_by_status(self):
        second = Job.objects.create(
            user=self.user, url="https://boards.greenhouse.io/acme/jobs/2",
            company="Beta", title="Platform", description="x",
        )
        Application.objects.create(user=self.user, job=second, status="SAVED")

        response = self.client.get("/api/applications/?status=INTERVIEW")
        self.assertEqual([r["id"] for r in response.json()], [self.application.id])

    def test_filter_by_status_is_case_insensitive(self):
        response = self.client.get("/api/applications/?status=interview")
        self.assertEqual(len(response.json()), 1)

    def test_malformed_status_filter_returns_empty_not_error(self):
        response = self.client.get("/api/applications/?status=NOT_A_STATUS")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_malformed_job_filter_returns_empty_not_error(self):
        response = self.client.get("/api/applications/?job=abc")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_summary_counts_match_the_list(self):
        second = Job.objects.create(
            user=self.user, url="https://boards.greenhouse.io/acme/jobs/3",
            company="C", title="D", description="x",
        )
        Application.objects.create(user=self.user, job=second, status="APPLIED")

        counts = self.client.get("/api/applications/?summary=1").json()
        self.assertEqual(counts["total"], 2)
        self.assertEqual(counts["counts"]["INTERVIEW"], 1)
        self.assertEqual(counts["counts"]["APPLIED"], 1)
        # Every known status is present even at zero, so the UI has no gaps.
        self.assertEqual(counts["counts"]["OFFER"], 0)
        self.assertIn("WITHDRAWN", counts["counts"])

    def test_summary_excludes_other_accounts(self):
        Application.objects.create(user=self.other, job=self.other_job)
        counts = self.client.get("/api/applications/?summary=1").json()
        self.assertEqual(counts["total"], 1)

    def test_list_does_not_n_plus_one(self):
        """
        Query count must not grow with the number of applications.

        Asserted as a constant rather than an exact number: session and auth
        lookups are framework overhead, but the application query itself must
        stay at one no matter how many rows are returned.
        """
        def measure(target, base):
            for index in range(target):
                job = Job.objects.create(
                    user=self.user,
                    url="https://boards.greenhouse.io/acme/jobs/%d" % (base + index),
                    company="C%d" % index, title="T", description="x",
                )
                Application.objects.create(
                    user=self.user, job=job, tailored_resume=self.resume
                )
            with CaptureQueriesContext(connection) as captured:
                self.client.get("/api/applications/")
            return len(captured)

        few = measure(2, 100)
        many = measure(6, 200)
        self.assertEqual(
            few, many, "the application list issued extra queries per row"
        )


class DetailTests(ApplicationTestCase):

    def setUp(self):
        super().setUp()
        self.application = Application.objects.create(
            user=self.user, job=self.job, status="SAVED"
        )

    def test_retrieve_own_application(self):
        response = self.client.get("/api/applications/%d/" % self.application.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.application.id)

    def test_cross_user_retrieve_is_404_not_403(self):
        self.client.logout()
        self.client.force_login(self.other)
        response = self.client.get("/api/applications/%d/" % self.application.id)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "Application not found")

    def test_unauthenticated_access_is_rejected(self):
        self.client.logout()
        self.assertIn(
            self.client.get("/api/applications/").status_code, (401, 403)
        )
        self.assertIn(
            self.client.get("/api/applications/%d/" % self.application.id).status_code,
            (401, 403),
        )

    def test_update_notes(self):
        response = patch_json(
            self.client,
            "/api/applications/%d/" % self.application.id,
            {"notes": "Recruiter mentioned a take-home."},
        )
        self.assertEqual(response.status_code, 200)
        self.application.refresh_from_db()
        self.assertEqual(
            self.application.notes, "Recruiter mentioned a take-home."
        )

    def test_cross_user_update_is_404_and_changes_nothing(self):
        self.client.logout()
        self.client.force_login(self.other)
        response = patch_json(
            self.client,
            "/api/applications/%d/" % self.application.id,
            {"status": "OFFER"},
        )
        self.assertEqual(response.status_code, 404)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, "SAVED")

    def test_delete_own_application(self):
        response = self.client.delete("/api/applications/%d/" % self.application.id)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Application.objects.filter(id=self.application.id).exists())

    def test_cross_user_delete_is_404_and_preserves_the_row(self):
        self.client.logout()
        self.client.force_login(self.other)
        response = self.client.delete("/api/applications/%d/" % self.application.id)
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Application.objects.filter(id=self.application.id).exists())

    def test_missing_application_is_404(self):
        self.assertEqual(
            self.client.get("/api/applications/999999/").status_code, 404
        )


class StatusTransitionTests(ApplicationTestCase):

    def setUp(self):
        super().setUp()
        self.application = Application.objects.create(
            user=self.user, job=self.job, status="SAVED"
        )

    def _move(self, status):
        return post_json(
            self.client,
            "/api/applications/%d/status/" % self.application.id,
            {"status": status},
        )

    def test_move_to_applied(self):
        response = self._move("APPLIED")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "APPLIED")

    def test_applied_at_is_stamped_once_and_never_overwritten(self):
        self._move("APPLIED")
        self.application.refresh_from_db()
        first = self.application.applied_at
        self.assertIsNotNone(first)

        self._move("INTERVIEW")
        self.application.refresh_from_db()
        self.assertEqual(self.application.applied_at, first)

    def test_saved_does_not_stamp_applied_at(self):
        self._move("SAVED")
        self.application.refresh_from_db()
        self.assertIsNone(self.application.applied_at)

    def test_full_pipeline_transition(self):
        for status in ("APPLIED", "ASSESSMENT", "INTERVIEW", "OFFER"):
            self.assertEqual(self._move(status).status_code, 200)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, "OFFER")

    def test_rejected_is_allowed(self):
        self.assertEqual(self._move("REJECTED").status_code, 200)

    def test_unknown_status_is_rejected(self):
        response = self._move("BANANA")
        self.assertEqual(response.status_code, 400)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, "SAVED")

    def test_status_is_case_insensitive(self):
        self.assertEqual(self._move("interview").json()["status"], "INTERVIEW")

    def test_cross_user_status_change_is_404(self):
        self.client.logout()
        self.client.force_login(self.other)
        response = self._move("OFFER")
        self.assertEqual(response.status_code, 404)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, "SAVED")

    def test_every_declared_status_is_accepted(self):
        for value, _label in Application.STATUS_CHOICES:
            self.assertEqual(self._move(value).status_code, 200, value)

    def test_status_field_cannot_be_set_to_arbitrary_string_on_patch(self):
        response = patch_json(
            self.client,
            "/api/applications/%d/" % self.application.id,
            {"status": "BANANA"},
        )
        self.assertEqual(response.status_code, 400)

    def test_tailoring_does_not_imply_applied(self):
        """Saving a tailored resume is not applying. The status stays SAVED."""
        self.assertEqual(self.application.status, "SAVED")
        self.assertIsNone(self.application.applied_at)

    def test_is_active_and_is_closed_helpers(self):
        self._move("INTERVIEW")
        self.application.refresh_from_db()
        self.assertTrue(self.application.is_active)
        self.assertFalse(self.application.is_closed)

        self._move("REJECTED")
        self.application.refresh_from_db()
        self.assertFalse(self.application.is_active)
        self.assertTrue(self.application.is_closed)


class DashboardTests(ApplicationTestCase):

    def test_empty_account_reports_zeros_not_missing_keys(self):
        # The shared fixture creates a job and a master resume, so remove them
        # to make this genuinely the empty-account case the name claims.
        Job.objects.all().delete()
        Resume.objects.all().delete()

        stats = dashboard_stats(self.user)
        self.assertEqual(stats["jobs"]["total"], 0)
        self.assertEqual(stats["applications"]["total"], 0)
        self.assertEqual(stats["applications"]["offers"], 0)
        self.assertIsNone(stats["match"]["average"])
        self.assertFalse(stats["resumes"]["has_master"])
        self.assertEqual(stats["recent_applications"], [])
        for value, _label in Application.STATUS_CHOICES:
            self.assertIn(value, stats["applications"]["by_status"])

    def test_statistics_come_from_real_rows(self):
        Application.objects.create(
            user=self.user, job=self.job, status="INTERVIEW"
        )
        second = Job.objects.create(
            user=self.user, url="https://boards.greenhouse.io/acme/jobs/2",
            company="Beta", title="Platform", description="x", match_score=70.0,
        )
        Application.objects.create(user=self.user, job=second, status="OFFER")

        stats = dashboard_stats(self.user)
        self.assertEqual(stats["jobs"]["total"], 2)
        self.assertEqual(stats["jobs"]["scored"], 2)
        self.assertEqual(stats["applications"]["total"], 2)
        self.assertEqual(stats["applications"]["interviews"], 1)
        self.assertEqual(stats["applications"]["offers"], 1)
        self.assertEqual(stats["match"]["average"], 78.0)

    def test_average_ignores_unscored_jobs(self):
        Job.objects.create(
            user=self.user, url="https://boards.greenhouse.io/acme/jobs/9",
            company="C", title="T", description="x", match_score=None,
        )
        self.assertEqual(dashboard_stats(self.user)["match"]["average"], 86.0)

    def test_dashboard_is_user_isolated(self):
        """The other account's rows must not move this account's numbers."""
        # Baseline: whatever the shared fixture gave this account.
        baseline = dashboard_stats(self.user)
        self.assertEqual(baseline["jobs"]["total"], 1)

        Application.objects.create(user=self.other, job=self.other_job, status="OFFER")
        Job.objects.create(
            user=self.other, url="https://boards.greenhouse.io/other/jobs/2",
            company="O", title="O", description="x", match_score=10.0,
        )

        stats = dashboard_stats(self.user)
        self.assertEqual(stats["jobs"]["total"], baseline["jobs"]["total"])
        self.assertEqual(
            stats["applications"]["total"], baseline["applications"]["total"]
        )
        self.assertEqual(stats["applications"]["offers"], 0)
        self.assertEqual(stats["match"]["average"], baseline["match"]["average"])

    def test_dashboard_endpoint_requires_authentication(self):
        self.client.logout()
        self.assertIn(
            self.client.get("/api/applications/dashboard/").status_code, (401, 403)
        )

    def test_dashboard_endpoint_returns_real_data(self):
        Application.objects.create(user=self.user, job=self.job, status="APPLIED")
        response = self.client.get("/api/applications/dashboard/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["applications"]["total"], 1)
        self.assertEqual(len(body["recent_applications"]), 1)
        self.assertEqual(body["recent_applications"][0]["job"]["company"], "Acme")

    def test_recent_applications_are_capped(self):
        for index in range(8):
            job = Job.objects.create(
                user=self.user,
                url="https://boards.greenhouse.io/acme/jobs/%d" % (200 + index),
                company="C%d" % index, title="T", description="x",
            )
            Application.objects.create(user=self.user, job=job)
        self.assertEqual(len(dashboard_stats(self.user)["recent_applications"]), 5)

    def test_recent_applications_do_not_n_plus_one(self):
        """
        The recent-applications block must not add a query per row.

        ``select_related("job", "tailored_resume")`` is what guarantees this, so
        the count is measured with two rows and with ten and compared.
        """
        def measure(count, base):
            for index in range(count):
                job = Job.objects.create(
                    user=self.user,
                    url="https://boards.greenhouse.io/acme/jobs/%d" % (base + index),
                    company="C%d" % index, title="T", description="x",
                )
                Application.objects.create(
                    user=self.user, job=job, tailored_resume=self.resume
                )
            with CaptureQueriesContext(connection) as captured:
                rows = dashboard_stats(self.user)["recent_applications"]
            return len(captured), len(rows)

        few_queries, few_rows = measure(2, 300)
        many_queries, many_rows = measure(8, 400)

        self.assertEqual(
            few_queries, many_queries,
            "recent_applications issued a query per row",
        )
        self.assertEqual(few_rows, 2)
        self.assertEqual(many_rows, 5, "capped at RECENT_LIMIT")
