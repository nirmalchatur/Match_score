"""
The AI run audit record.

The state machine is asserted directly, and the interesting cases are the ones
that would let a bad run look good: a rejected result must not be recorded as a
success, a deleted artifact must not erase the record that a run happened, and
no credential may be recoverable from any column.
"""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.ai import factory, prompts
from apps.ai.exceptions import (
    AIConfigurationError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
    AITailoringValidationError,
)
from apps.ai.models import AIRun
from apps.ai.providers.fake import FakeAIProvider
from apps.ai.runs import AIRunRecorder, failure_category_for
from apps.ai.tests.fixtures import SOURCE_PROFILE, valid_payload
from apps.jobs.models import Job
from apps.resumes.models import Resume, ResumeProfile
from apps.resumes.services import tailoring_service
from apps.users.models import ProviderCredential
from apps.users.tests.test_ai_credentials import FAKE_KEY

User = get_user_model()


class AIRunTestCase(TestCase):
    """One account with a master resume and one analysed job."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="runs@example.test", email="runs@example.test", password="pw-runs-1234"
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
            url="https://boards.greenhouse.io/acme/jobs/9",
            company="Acme",
            title="Backend Engineer",
            description="Build services with Django and PostgreSQL. Docker required.",
            match_score=71.0,
            match_result={"score": 71.0, "decision": "TAILOR"},
        )

    def use_provider(self, payload=None, provider_class=FakeAIProvider):
        provider = provider_class(
            json.dumps(payload if payload is not None else valid_payload())
        )
        factory.register("test_fake", lambda: provider)
        self.addCleanup(factory._registry.pop, "test_fake", None)
        return provider

    def tailoring_run(self):
        return AIRun.objects.filter(
            user=self.user, operation=AIRun.OPERATION_RESUME_TAILORING
        )


class StateMachineTests(AIRunTestCase):
    """The legal moves, and the illegal ones."""

    def make(self, status=AIRun.PENDING):
        return AIRun.objects.create(
            user=self.user,
            operation=AIRun.OPERATION_RESUME_TAILORING,
            status=status,
        )

    def test_a_new_run_is_pending_and_not_terminal(self):
        run = self.make()
        self.assertEqual(run.status, AIRun.PENDING)
        self.assertFalse(run.is_terminal)

    def test_running_stamps_a_start_time(self):
        run = self.make()
        run.mark_running()

        self.assertEqual(run.status, AIRun.RUNNING)
        self.assertIsNotNone(run.started_at)

    def test_succeeding_stamps_a_completion_and_a_duration(self):
        run = self.make()
        run.mark_running()
        run.mark_succeeded(validation_status="valid")

        self.assertEqual(run.status, AIRun.SUCCEEDED)
        self.assertTrue(run.is_terminal)
        self.assertEqual(run.validation_status, "valid")
        self.assertIsNotNone(run.completed_at)
        self.assertIsNotNone(run.duration_ms)

    def test_pending_can_fail_without_ever_running(self):
        """
        A run that dies before the provider is resolved -- no key, no provider,
        no master resume -- never reaches RUNNING. Recording it as pending
        forever would hide a configuration error behind a spinner.
        """
        run = self.make()
        run.mark_failed(AIRun.FAILURE_CONFIGURATION, error_code="ai_not_configured")

        self.assertEqual(run.status, AIRun.FAILED)
        self.assertEqual(run.failure_category, AIRun.FAILURE_CONFIGURATION)

    def test_terminal_states_do_not_move(self):
        for status in (AIRun.SUCCEEDED, AIRun.FAILED, AIRun.CANCELLED):
            with self.subTest(status=status):
                run = self.make(status)
                self.assertFalse(run.can_transition_to(AIRun.RUNNING))
                with self.assertRaises(ValueError):
                    run.transition_to(AIRun.RUNNING)

    def test_running_cannot_restart_itself(self):
        """A self-transition would reset started_at and lose the real start."""
        run = self.make(AIRun.RUNNING)
        original_start = run.started_at

        with self.assertRaises(ValueError):
            run.mark_running()

        self.assertEqual(run.started_at, original_start)

    def test_an_unknown_failure_category_becomes_internal(self):
        run = self.make()
        run.mark_failed("SOMETHING_NEW", error_code="x")

        self.assertEqual(run.failure_category, AIRun.FAILURE_INTERNAL)

    def test_cancelled_is_not_a_failure(self):
        run = self.make()
        run.mark_cancelled()

        self.assertEqual(run.status, AIRun.CANCELLED)
        self.assertEqual(run.failure_category, "")


class FailureCategoryTests(AIRunTestCase):
    """Every AI error has a bucket, and nothing is free text."""

    def test_known_errors_map_to_their_bucket(self):
        from apps.ai.exceptions import (
            AIProviderResponseError,
            AITailoringValidationError,
        )

        expected = {
            AIConfigurationError: AIRun.FAILURE_CONFIGURATION,
            AIProviderUnavailableError: AIRun.FAILURE_PROVIDER_UNAVAILABLE,
            AIProviderTimeoutError: AIRun.FAILURE_PROVIDER_TIMEOUT,
            AIProviderResponseError: AIRun.FAILURE_INVALID_RESPONSE,
            AITailoringValidationError: AIRun.FAILURE_VALIDATION_FAILED,
        }

        for exc, category in expected.items():
            with self.subTest(exception=exc.__name__):
                self.assertEqual(failure_category_for(exc("message")), category)

    def test_an_unexpected_exception_is_internal(self):
        self.assertEqual(
            failure_category_for(RuntimeError("boom")), AIRun.FAILURE_INTERNAL
        )


class NamedProvider(FakeAIProvider):
    """
    A double that describes itself the way the real providers do.

    ``describe()`` is the same method the status endpoint exposes to a browser,
    and a real one carries the model name. The extra ``base_url`` here is the
    point: it is the kind of configuration a provider knows and an audit row
    must not.
    """

    name = "named"
    display_name = "Named provider"

    def describe(self):
        return {
            "provider": self.name,
            "display_name": self.display_name,
            "model": "test-model-1",
            "base_url": "http://internal-ollama-host:11434",
        }


class RecorderTests(AIRunTestCase):
    """The recorder writes the row, and never breaks the block it wraps."""

    def record(self, **kwargs):
        options = {
            "user": self.user,
            "operation": AIRun.OPERATION_RESUME_TAILORING,
            "prompt_version": "tailoring-1",
            "source_resume": self.master,
            "source_job": self.job,
        }
        options.update(kwargs)
        return AIRunRecorder(**options)

    def test_a_successful_block_leaves_a_succeeded_row(self):
        with self.record() as recorder:
            recorder.attach_validation("valid")

        run = self.tailoring_run().get()

        self.assertEqual(run.status, AIRun.SUCCEEDED)
        self.assertEqual(run.validation_status, "valid")
        self.assertEqual(run.attempts, 1)
        self.assertEqual(run.prompt_version, "tailoring-1")
        self.assertEqual(run.source_resume_id, self.master.id)
        self.assertEqual(run.source_job_id, self.job.id)
        self.assertIsNotNone(run.started_at)
        self.assertIsNotNone(run.completed_at)
        self.assertIsNotNone(run.duration_ms)
        self.assertEqual(recorder.run_id, run.id)

    def test_a_failed_block_records_the_bucket_and_still_raises(self):
        with self.assertRaises(AIProviderTimeoutError):
            with self.record():
                raise AIProviderTimeoutError("The AI provider took too long.")

        run = self.tailoring_run().get()

        self.assertEqual(run.status, AIRun.FAILED)
        self.assertEqual(run.failure_category, AIRun.FAILURE_PROVIDER_TIMEOUT)
        self.assertEqual(run.error_code, "ai_timeout")
        # A code, never a message: the message is where base URLs and provider
        # bodies live.
        self.assertNotIn("too long", run.error_code)

    def test_an_interrupt_is_cancelled_not_a_provider_failure(self):
        with self.assertRaises(KeyboardInterrupt):
            with self.record():
                raise KeyboardInterrupt

        run = self.tailoring_run().get()
        self.assertEqual(run.status, AIRun.CANCELLED)
        self.assertEqual(run.failure_category, "")

    def test_a_disabled_recorder_touches_no_table(self):
        with self.record(enabled=False) as recorder:
            recorder.attach_validation("valid")

        self.assertIsNone(recorder.run)
        self.assertEqual(self.tailoring_run().count(), 0)

    def test_the_provider_identity_is_stored_and_its_configuration_is_not(self):
        with self.record() as recorder:
            recorder.use_provider(NamedProvider())

        run = self.tailoring_run().get()
        dumped = json.dumps(run.__dict__, default=str)

        self.assertEqual(run.provider, "named")
        self.assertEqual(run.model, "test-model-1")
        self.assertNotIn("internal-ollama-host", dumped)

    def test_attach_result_links_the_artifact(self):
        tailored = Resume.objects.create(
            user=self.user, name="Tailored", resume_type="TAILORED"
        )

        with self.record() as recorder:
            recorder.attach_result(tailored)

        run = self.tailoring_run().get()
        self.assertEqual(run.result_resume_id, tailored.id)


@override_settings(AI_PROVIDER="test_fake")
class TailoringAuditIntegrationTests(AIRunTestCase):
    """
    The audit trail as a user experiences it: through the real pipeline.

    These drive the service rather than the recorder, because the question is
    not "can a row be written" but "does the row describe what actually
    happened" -- and the answer has to survive a rejected result, a dead
    provider and a missing key.
    """

    def test_a_successful_tailoring_records_a_succeeded_run(self):
        self.use_provider()

        tailoring_service.generate_tailoring(self.user, self.job.id)

        run = self.tailoring_run().get()
        self.assertEqual(run.status, AIRun.SUCCEEDED)
        self.assertEqual(run.provider, "fake")
        self.assertEqual(run.validation_status, "valid")
        self.assertEqual(run.prompt_version, prompts.PROMPT_VERSION)
        self.assertEqual(run.source_resume_id, self.master.id)
        self.assertEqual(run.source_job_id, self.job.id)
        self.assertEqual(run.attempts, 1)
        # Empty, not null: the column is a closed choice set, so a filter for a
        # category can never accidentally match a run that is still going.
        self.assertEqual(run.failure_category, "")

    def test_a_rejected_result_is_a_validation_failure_and_saves_nothing(self):
        payload = valid_payload()
        payload["experience"][0]["tailored_bullets"] = [
            "Cut p99 latency by 95% across the platform."
        ]
        self.use_provider(payload)

        with self.assertRaises(AITailoringValidationError):
            tailoring_service.generate_tailoring(self.user, self.job.id)

        run = self.tailoring_run().get()
        self.assertEqual(run.status, AIRun.FAILED)
        self.assertEqual(run.failure_category, AIRun.FAILURE_VALIDATION_FAILED)
        self.assertEqual(run.validation_status, "rejected")

        # The important half: a failed run leaves no artifact behind, and
        # nothing is marked approved.
        self.assertFalse(
            Resume.objects.filter(user=self.user, resume_type="TAILORED").exists()
        )

    def test_a_provider_failure_leaves_the_job_and_the_master_untouched(self):
        provider = FakeAIProvider.timing_out()
        factory.register("test_fake", lambda: provider)
        self.addCleanup(factory._registry.pop, "test_fake", None)

        with self.assertRaises(AIProviderTimeoutError):
            tailoring_service.generate_tailoring(self.user, self.job.id)

        run = self.tailoring_run().get()
        self.assertEqual(run.status, AIRun.FAILED)
        self.assertEqual(run.failure_category, AIRun.FAILURE_PROVIDER_TIMEOUT)
        self.assertEqual(run.error_code, "ai_timeout")

        self.job.refresh_from_db()
        self.assertEqual(self.job.match_score, 71.0)
        self.assertEqual(self.job.match_result, {"score": 71.0, "decision": "TAILOR"})

        self.master.refresh_from_db()
        self.assertTrue(self.master.is_master)
        self.assertEqual(self.master.resume_type, "MASTER")
        self.assertFalse(
            Resume.objects.filter(user=self.user, resume_type="TAILORED").exists()
        )

    def test_an_unconfigured_deployment_is_recorded_as_a_configuration_failure(self):
        """
        The failure a user is most likely to meet, and the one a log line alone
        answers worst: "AI is not configured" and "the model is not pulled" read
        the same from the browser.
        """
        with override_settings(AI_PROVIDER=""):
            with self.assertRaises(AIConfigurationError):
                tailoring_service.generate_tailoring(self.user, self.job.id)

        run = self.tailoring_run().get()
        self.assertEqual(run.status, AIRun.FAILED)
        self.assertEqual(run.failure_category, AIRun.FAILURE_CONFIGURATION)
        self.assertEqual(run.error_code, "ai_not_configured")
        self.assertEqual(run.provider, "")

    def test_saving_links_the_artifact_to_the_run_that_produced_it(self):
        self.use_provider()
        payload = tailoring_service.generate_tailoring(self.user, self.job.id)

        tailored, _validation = tailoring_service.save_tailored_resume(
            self.user, self.job.id, payload["result"], provider_name="fake"
        )

        run = self.tailoring_run().get()
        self.assertEqual(run.status, AIRun.SUCCEEDED)
        self.assertEqual(run.result_resume_id, tailored.id)

    def test_no_credential_reaches_any_column_of_a_run(self):
        credential = ProviderCredential.objects.create(user=self.user, provider="gemini")
        # Saved, not just staged: a row created and never written would make
        # this assertion pass for the wrong reason.
        credential.set_key(FAKE_KEY)
        credential.save()

        self.use_provider()

        tailoring_service.generate_tailoring(self.user, self.job.id)

        run = self.tailoring_run().get()
        dumped = json.dumps(
            {**run.__dict__, **run.public_dict()},
            default=str,
        )

        self.assertNotIn(FAKE_KEY, dumped)
        self.assertNotIn("encrypted", dumped)
