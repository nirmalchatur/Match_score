"""
The activity record.

It has no endpoint in this phase, so these tests are the read surface: they
assert what is written for a real user action, that nothing sensitive is ever
stored, and that the record is owner-scoped like every other table here.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from apps.common.models import ActivityEvent

User = get_user_model()


def make_user(email="activity@example.test"):
    return User.objects.create_user(username=email, email=email, password="pw-activity-1234")


class RecordTests(TestCase):
    """The writer's contract."""

    def setUp(self):
        self.user = make_user()

    def test_records_one_row_with_the_fields_it_was_given(self):
        event = ActivityEvent.record(
            self.user,
            ActivityEvent.RESUME_UPLOADED,
            object_type="resume",
            object_id=42,
            summary="Master resume",
            metadata={"skills": 12},
        )

        self.assertIsNotNone(event)
        self.assertEqual(event.user_id, self.user.pk)
        self.assertEqual(event.action, "RESUME_UPLOADED")
        self.assertEqual(event.object_type, "resume")
        self.assertEqual(event.object_id, 42)
        self.assertEqual(event.summary, "Master resume")
        self.assertEqual(event.metadata["skills"], 12)

    def test_an_unknown_action_is_refused_rather_than_stored(self):
        """
        Free-text actions would make the stream unqueryable within a release.
        A typo is a programming error, so it is dropped noisily.
        """
        event = ActivityEvent.record(self.user, "TAILORED_EVERYTHING")

        self.assertIsNone(event)
        self.assertEqual(ActivityEvent.objects.count(), 0)

    def test_an_anonymous_user_is_not_recorded(self):
        self.assertIsNone(
            ActivityEvent.record(AnonymousUser(), ActivityEvent.RESUME_UPLOADED)
        )
        self.assertEqual(ActivityEvent.objects.count(), 0)

    def test_object_id_junk_becomes_null_rather_than_raising(self):
        event = ActivityEvent.record(
            self.user,
            ActivityEvent.JOB_ANALYSED,
            object_id="not-an-id",
        )
        self.assertIsNone(event.object_id)

    def test_a_long_summary_is_truncated(self):
        event = ActivityEvent.record(
            self.user,
            ActivityEvent.JOB_ANALYSED,
            summary="x" * 500,
        )
        self.assertEqual(len(event.summary), ActivityEvent.MAX_SUMMARY)


class MetadataHygieneTests(TestCase):
    """Metadata is for identifiers and counts, not for secrets or documents."""

    def setUp(self):
        self.user = make_user()

    def test_secret_named_keys_are_dropped_entirely(self):
        event = ActivityEvent.record(
            self.user,
            ActivityEvent.TAILORING_GENERATED,
            metadata={
                "provider": "gemini",
                # Short, but the same prefixes the redactor tests use: a
                # credential-shaped literal this long is what the repository's
                # secret scan exists to catch, and it should not have to allowlist
                # a test fixture to keep passing.
                "api_key": "AIza1234",
                "session_key": "abc123",
            },
        )

        self.assertEqual(event.metadata, {"provider": "gemini"})
        # Not masked -- absent. A "[redacted]" marker in a JSON column is a
        # promise that something was there.
        self.assertNotIn("api_key", event.metadata)

    def test_a_secret_shaped_value_is_dropped_under_any_name(self):
        event = ActivityEvent.record(
            self.user,
            ActivityEvent.TAILORING_GENERATED,
            metadata={"note": "gsk_1234567890abcdefghijklmnopqrstuvwxyz"},
        )
        self.assertEqual(event.metadata, {})

    def test_nested_structures_are_not_stored(self):
        """A nested structure is a payload, and a payload here is a resume."""
        event = ActivityEvent.record(
            self.user,
            ActivityEvent.TAILORING_GENERATED,
            metadata={
                "resume": {"skills": ["python"]},
                "bullets": ["did a thing"],
                "matches": 4,
            },
        )

        self.assertEqual(event.metadata, {"matches": 4})

    def test_long_metadata_strings_are_truncated(self):
        event = ActivityEvent.record(
            self.user,
            ActivityEvent.JOB_ANALYSED,
            metadata={"model": "m" * 400},
        )
        self.assertEqual(len(event.metadata["model"]), ActivityEvent.MAX_METADATA_VALUE)


class OwnershipTests(TestCase):
    """The same tenant rule as every other model: owner-scoped, always."""

    def test_events_are_only_visible_to_their_owner(self):
        alice = make_user("alice.activity@example.test")
        bob = make_user("bob.activity@example.test")

        alice_event = ActivityEvent.record(alice, ActivityEvent.RESUME_UPLOADED)
        bob_event = ActivityEvent.record(bob, ActivityEvent.RESUME_UPLOADED)

        alice_sees = set(ActivityEvent.objects.filter(user=alice).values_list("id", flat=True))

        self.assertEqual(alice_sees, {alice_event.id})
        self.assertNotIn(bob_event.id, alice_sees)

    def test_deleting_the_account_takes_its_history_with_it(self):
        user = make_user("gone@example.test")
        ActivityEvent.record(user, ActivityEvent.RESUME_UPLOADED)

        user.delete()

        self.assertEqual(ActivityEvent.objects.count(), 0)
