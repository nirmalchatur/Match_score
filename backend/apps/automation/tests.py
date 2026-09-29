"""
Tests for the notification service.

The three properties worth defending are the ones that would break silently:

1. Tenant isolation -- one user cannot read or mutate another's notifications.
2. De-duplication -- a repeated event does not produce a second row.
3. Preferences -- a user who switched something off is not notified anyway.

Everything else is plumbing tested to keep coverage honest, but those three are
the reason this file is not shorter.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Notification, NotificationPreference
from .tasks import emit, job_analysed

User = get_user_model()


class NotificationModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="alice",
            email="alice@example.com",
            password="test-password-123",
        )
        self.other = User.objects.create_user(
            username="bob",
            email="bob@example.com",
            password="test-password-123",
        )

    def test_notify_creates_row(self):
        row = Notification.notify(
            self.user, Notification.KIND_INFO, "Hello", body="World"
        )
        self.assertIsNotNone(row)
        self.assertEqual(row.user, self.user)
        self.assertFalse(row.is_read)

    def test_notify_ignores_anonymous_user(self):
        self.assertIsNone(
            Notification.notify(AnonymousUser(), Notification.KIND_INFO, "Hi")
        )

    def test_dedupe_key_prevents_second_row(self):
        first = Notification.notify(
            self.user,
            Notification.KIND_SUCCESS,
            "Job analysed",
            dedupe_key="job-analysed:7:DONE",
        )
        second = Notification.notify(
            self.user,
            Notification.KIND_SUCCESS,
            "Job analysed",
            dedupe_key="job-analysed:7:DONE",
        )
        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 1)

    def test_blank_dedupe_key_never_collides(self):
        # The unique constraint is conditional on a non-empty key, so two
        # unrelated blank-key rows must both be allowed. This is exactly the
        # case an unconditional constraint would break.
        Notification.notify(self.user, Notification.KIND_WARNING, "One")
        Notification.notify(self.user, Notification.KIND_WARNING, "Two")
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 2)

    def test_dedupe_key_is_scoped_per_user(self):
        # Bob's event about job 7 is not Alice's event about job 7.
        a = Notification.notify(
            self.user, Notification.KIND_SUCCESS, "A", dedupe_key="k1"
        )
        b = Notification.notify(
            self.other, Notification.KIND_SUCCESS, "B", dedupe_key="k1"
        )
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)

    def test_mark_read_is_idempotent(self):
        row = Notification.notify(self.user, Notification.KIND_INFO, "Hi")
        self.assertTrue(row.mark_read())
        self.assertFalse(row.mark_read())
        self.assertIsNotNone(row.read_at)

    def test_title_is_truncated_to_column_width(self):
        # A long job title must not raise on Postgres, where VARCHAR(120) is
        # enforced strictly rather than silently truncated.
        row = Notification.notify(self.user, Notification.KIND_INFO, "x" * 400)
        self.assertEqual(len(row.title), 120)

    def test_partial_unique_constraint_blocks_duplicate_key(self):
        # Bypasses notify() to prove the database is the backstop, not only the
        # application-level pre-check.
        Notification.objects.create(
            user=self.user,
            kind=Notification.KIND_SUCCESS,
            title="first",
            dedupe_key="job-analysed:7:DONE",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Notification.objects.create(
                    user=self.user,
                    kind=Notification.KIND_SUCCESS,
                    title="second",
                    dedupe_key="job-analysed:7:DONE",
                )


class NotificationPreferenceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="carol",
            email="carol@example.com",
            password="test-password-123",
        )

    def test_defaults_created_on_first_access(self):
        prefs = NotificationPreference.for_user(self.user)
        self.assertTrue(prefs.job_updates)
        self.assertTrue(prefs.job_matches)
        self.assertTrue(prefs.application_updates)

    def test_for_user_is_stable_across_calls(self):
        a = NotificationPreference.for_user(self.user)
        b = NotificationPreference.for_user(self.user)
        self.assertEqual(a.pk, b.pk)

    def test_allows_respects_switch(self):
        # All three off means silence for every kind, including errors: at that
        # point the user has opted out of the feature entirely.
        prefs = NotificationPreference.for_user(self.user)
        prefs.job_updates = False
        prefs.job_matches = False
        prefs.application_updates = False
        prefs.save()

        reloaded = NotificationPreference.for_user(self.user)
        for kind in (
            Notification.KIND_INFO,
            Notification.KIND_SUCCESS,
            Notification.KIND_WARNING,
            Notification.KIND_ERROR,
        ):
            self.assertFalse(reloaded.allows(kind), kind)

    def test_turning_off_job_updates_keeps_failures_visible(self):
        # Switching off routine job chatter must not also hide a real failure.
        # This is the case a naive "INFO maps to one flag" mapping gets wrong.
        prefs = NotificationPreference.for_user(self.user)
        prefs.job_updates = False
        prefs.save()

        reloaded = NotificationPreference.for_user(self.user)
        self.assertFalse(reloaded.allows(Notification.KIND_INFO))
        self.assertTrue(reloaded.allows(Notification.KIND_ERROR))

    def test_suppressed_event_creates_nothing(self):
        prefs = NotificationPreference.for_user(self.user)
        prefs.job_updates = False
        prefs.job_matches = False
        prefs.application_updates = False
        prefs.save()

        emit(self.user, Notification.KIND_ERROR, "Analysis failed")

        self.assertEqual(Notification.objects.filter(user=self.user).count(), 0)

    def test_error_survives_when_only_job_updates_is_off(self):
        prefs = NotificationPreference.for_user(self.user)
        prefs.job_updates = False
        prefs.save()

        emit(self.user, Notification.KIND_ERROR, "Analysis failed")

        self.assertEqual(Notification.objects.filter(user=self.user).count(), 1)


class EmitTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="dave",
            email="dave@example.com",
            password="test-password-123",
        )

    def test_emit_creates_notification(self):
        emit(self.user, Notification.KIND_SUCCESS, "Saved resume", dedupe_key="k")
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 1)

    def test_emit_is_idempotent_for_keyed_events(self):
        # The poller case: the same observation arriving repeatedly.
        for _ in range(3):
            emit(
                self.user,
                Notification.KIND_SUCCESS,
                "Analysis finished",
                dedupe_key="job-analysed:1:DONE",
            )
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 1)

    def test_job_analysed_includes_score_in_body(self):
        class FakeJob:
            pk = 3
            title = "Backend Engineer"
            company = "Acme"
            match_score = 82.4
            status = "DONE"

        job_analysed(self.user, FakeJob())

        row = Notification.objects.get(user=self.user)
        self.assertIn("82", row.body)
        self.assertIn("Acme", row.title)

    def test_job_analysed_without_score_still_notifies(self):
        class FakeJob:
            pk = 4
            title = "Data Analyst"
            company = "Globex"
            match_score = None
            status = "DONE"

        job_analysed(self.user, FakeJob())
        row = Notification.objects.get(user=self.user)
        self.assertIn("Analysis finished", row.body)

    def test_emit_survives_a_broken_recipient(self):
        # A notification failure must not propagate into the caller's success
        # path. The emitter is called from inside real endpoints.
        class Exploding:
            pk = 1
            is_authenticated = True

            def __getattr__(self, name):
                raise RuntimeError("boom")

        emit(Exploding(), Notification.KIND_INFO, "should not raise")


class NotificationApiTests(TestCase):
    """Endpoint behaviour, weighted towards the cross-account cases."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="erin",
            email="erin@example.com",
            password="test-password-123",
        )
        self.other = User.objects.create_user(
            username="frank",
            email="frank@example.com",
            password="test-password-123",
        )
        self.client.force_authenticate(self.user)

    def test_list_requires_authentication(self):
        anonymous = APIClient()
        # (401, 403) rather than a bare 401: this project authenticates with
        # SessionAuthentication, which returns 403 for an unauthenticated
        # request because no WWW-Authenticate challenge is applicable. The
        # assertion is "rejected", not "rejected in this exact way".
        self.assertIn(
            anonymous.get("/api/notifications/").status_code, (401, 403)
        )

    def test_list_returns_own_rows_and_count(self):
        Notification.notify(self.user, Notification.KIND_INFO, "Mine")
        Notification.notify(self.user, Notification.KIND_INFO, "Also mine")
        Notification.notify(self.other, Notification.KIND_INFO, "Not mine")

        response = self.client.get("/api/notifications/")

        self.assertEqual(response.status_code, 200)
        titles = [r["title"] for r in response.data["results"]]
        self.assertEqual(sorted(titles), ["Also mine", "Mine"])
        self.assertEqual(response.data["unread_count"], 2)

    def test_list_can_filter_to_unread(self):
        read = Notification.notify(self.user, Notification.KIND_INFO, "Read")
        read.mark_read()
        Notification.notify(self.user, Notification.KIND_INFO, "Unread")

        response = self.client.get("/api/notifications/?unread=true")

        self.assertEqual([r["title"] for r in response.data["results"]], ["Unread"])

    def test_list_never_includes_the_user_field(self):
        Notification.notify(self.user, Notification.KIND_INFO, "Mine")
        response = self.client.get("/api/notifications/")
        self.assertNotIn("user", response.data["results"][0])

    def test_read_all_marks_only_my_rows(self):
        mine = Notification.notify(self.user, Notification.KIND_INFO, "Mine")
        theirs = Notification.notify(self.other, Notification.KIND_INFO, "Theirs")

        response = self.client.post("/api/notifications/read-all/")

        self.assertEqual(response.status_code, 200)
        mine.refresh_from_db()
        theirs.refresh_from_db()
        self.assertTrue(mine.is_read)
        self.assertFalse(theirs.is_read)

    def test_mark_read_marks_my_row(self):
        row = Notification.notify(self.user, Notification.KIND_INFO, "Mine")
        response = self.client.post(f"/api/notifications/{row.pk}/read/")
        self.assertEqual(response.status_code, 200)
        row.refresh_from_db()
        self.assertTrue(row.is_read)

    def test_cannot_mark_another_users_notification_read(self):
        # The core isolation guarantee. A 404 rather than a 403 on purpose: a
        # 403 would confirm the id exists, leaking a little about another
        # account's activity for no benefit to the caller.
        theirs = Notification.notify(self.other, Notification.KIND_INFO, "Theirs")
        response = self.client.post(f"/api/notifications/{theirs.pk}/read/")

        self.assertEqual(response.status_code, 404)
        theirs.refresh_from_db()
        self.assertFalse(theirs.is_read)

    def test_mark_read_on_missing_id_is_404(self):
        response = self.client.post("/api/notifications/999999/read/")
        self.assertEqual(response.status_code, 404)

    def test_preferences_get_reports_effective_defaults(self):
        response = self.client.get("/api/notifications/preferences/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["job_updates"])
        self.assertTrue(response.data["job_matches"])
        self.assertTrue(response.data["application_updates"])

    def test_preferences_patch_persists(self):
        response = self.client.patch(
            "/api/notifications/preferences/",
            {"job_matches": False},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["job_matches"])
        self.assertTrue(response.data["job_updates"])

    def test_preferences_patch_ignores_unknown_fields(self):
        # The allowlist is the point: a PATCH must not be able to write an
        # unrelated attribute.
        response = self.client.patch(
            "/api/notifications/preferences/",
            {"user": 1, "is_staff": True},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)

    def test_preferences_require_authentication(self):
        anonymous = APIClient()
        self.assertIn(
            anonymous.get("/api/notifications/preferences/").status_code,
            (401, 403),
        )

        # A notification failure must not propagate into the caller's success
        # path. The emitter is called from inside real endpoints.
        class Exploding:
            pk = 1
            is_authenticated = True

            def __getattr__(self, name):
                raise RuntimeError("boom")

        emit(Exploding(), Notification.KIND_INFO, "should not raise")

        # Bypasses notify() to prove the database is the backstop, not only the
        # application-level pre-check.
        Notification.objects.create(
            user=self.user,
            kind=Notification.KIND_SUCCESS,
            title="first",
            dedupe_key="job-analysed:7:DONE",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Notification.objects.create(
                    user=self.user,
                    kind=Notification.KIND_SUCCESS,
                    title="second",
                    dedupe_key="job-analysed:7:DONE",
                )
