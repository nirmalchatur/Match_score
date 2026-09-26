"""
Factual-validation tests.

Each test drives one fabrication the validator is meant to catch, and asserts on
the resulting verdict and violation code. ``ResumeTailor`` is exercised end to end
too, because the reject/return policy lives there rather than in the validator.
"""

import json

from django.test import SimpleTestCase, override_settings

from apps.ai import factory, validators
from apps.ai.exceptions import (
    AIConfigurationError,
    AITailoringValidationError,
)
from apps.ai.providers.fake import FakeAIProvider
from apps.ai.schemas import parse_tailoring_response
from apps.ai.tailor import ResumeTailor, build_source_resume

from .fixtures import JOB, JD_PROFILE, MATCH, SOURCE_PROFILE, valid_payload


def _validate(mutate=None):
    """Parse the canonical payload (optionally mutated) and validate it."""
    payload = valid_payload()
    if mutate:
        mutate(payload)
    result = parse_tailoring_response(json.dumps(payload))
    return validators.validate(result, build_source_resume(SOURCE_PROFILE))


def _codes(outcome):
    return {v.code for v in outcome.violations}


def _tailor(mutate=None):
    payload = valid_payload()
    if mutate:
        mutate(payload)
    return ResumeTailor.tailor_resume(
        SOURCE_PROFILE, JOB, MATCH,
        jd_profile=JD_PROFILE,
        provider=FakeAIProvider(json.dumps(payload)),
    )


class SourceResumeTests(SimpleTestCase):
    """The source view handed to the model, and to the validator."""

    def test_ids_are_minted_deterministically(self):
        first = build_source_resume(SOURCE_PROFILE)
        second = build_source_resume(SOURCE_PROFILE)
        self.assertEqual(first, second)
        self.assertEqual(first["experience"][0]["id"], "exp-0")
        self.assertEqual(first["projects"][0]["id"], "proj-0")

    def test_bullets_are_split_and_unmarked(self):
        source = build_source_resume(SOURCE_PROFILE)
        bullets = source["experience"][0]["bullets"]
        self.assertIn("Built internal REST API services using Django and PostgreSQL.", bullets)
        self.assertFalse(any(b.startswith("- ") for b in bullets))

    def test_project_name_and_bullets_are_separated(self):
        project = build_source_resume(SOURCE_PROFILE)["projects"][0]
        self.assertEqual(project["name"], "Resume Parser")
        self.assertEqual(len(project["bullets"]), 1)

    def test_empty_profile_does_not_crash(self):
        source = build_source_resume({})
        self.assertEqual(source["experience"], [])
        self.assertEqual(source["projects"], [])


class ValidResultTests(SimpleTestCase):
    def test_clean_result_is_valid(self):
        outcome = _validate()
        self.assertEqual(outcome.status, validators.VALID, outcome.as_dict())
        self.assertFalse(outcome.needs_review)

    def test_service_returns_clean_result(self):
        outcome = _tailor()
        self.assertEqual(outcome.validation.status, validators.VALID)
        self.assertEqual(outcome.result.experience[0].entry_id, "exp-0")

    def test_service_exposes_source_for_review(self):
        outcome = _tailor()
        self.assertEqual(outcome.source["experience"][0]["id"], "exp-0")
        self.assertEqual(outcome.provider["provider"], "fake")


class FabricationTests(SimpleTestCase):
    """Content the source resume does not support."""

    def test_fabricated_metric_is_rejected(self):
        def mutate(p):
            p["experience"][0]["tailored_bullets"] = [
                "Cut p99 latency by 95% across the platform."
            ]
        outcome = _validate(mutate)
        self.assertEqual(outcome.status, validators.REJECTED)
        self.assertIn("fabricated_metric", _codes(outcome))

    def test_fabricated_technology_is_rejected(self):
        def mutate(p):
            p["experience"][0]["tailored_bullets"] = [
                "Migrated the platform to Kubernetes and Docker."
            ]
        outcome = _validate(mutate)
        self.assertEqual(outcome.status, validators.REJECTED)
        self.assertIn("fabricated_technology", _codes(outcome))

    def test_fabricated_certification_is_rejected(self):
        def mutate(p):
            p["experience"][0]["tailored_bullets"] = [
                "AWS Certified solutions architect for the platform team."
            ]
        outcome = _validate(mutate)
        self.assertEqual(outcome.status, validators.REJECTED)
        self.assertIn("fabricated_certification", _codes(outcome))

    def test_fabricated_metric_in_summary_is_rejected(self):
        def mutate(p):
            p["summary"]["tailored"] = "Backend engineer who led a team of 50 engineers."
        outcome = _validate(mutate)
        self.assertEqual(outcome.status, validators.REJECTED)
        self.assertIn("fabricated_metric", _codes(outcome))

    def test_fabricated_technology_in_summary_is_rejected(self):
        def mutate(p):
            p["summary"]["tailored"] = "Backend engineer working with Kubernetes."
        outcome = _validate(mutate)
        self.assertEqual(outcome.status, validators.REJECTED)
        self.assertIn("fabricated_technology", _codes(outcome))

    def test_unsupported_skill_emphasis_is_rejected(self):
        def mutate(p):
            p["skills"]["emphasized"] = ["kubernetes"]
        outcome = _validate(mutate)
        self.assertEqual(outcome.status, validators.REJECTED)
        self.assertIn("unsupported_skill_emphasis", _codes(outcome))

    def test_unsupported_requirement_claimed_in_bullet_is_rejected(self):
        """Listing a requirement as unsupported *and* writing it is self-contradiction."""
        def mutate(p):
            p["skills"]["unsupported_requirements"] = ["kubernetes orchestration"]
            p["experience"][0]["tailored_bullets"] = [
                "Ran kubernetes in production for the platform team."
            ]
        outcome = _validate(mutate)
        self.assertEqual(outcome.status, validators.REJECTED)
        self.assertIn("unsupported_requirement_claimed", _codes(outcome))

    def test_unknown_entry_id_is_rejected(self):
        def mutate(p):
            p["experience"][0]["experience_id"] = "exp-99"
        outcome = _validate(mutate)
        self.assertEqual(outcome.status, validators.REJECTED)
        self.assertIn("unknown_entry_id", _codes(outcome))

    def test_project_id_must_also_exist(self):
        def mutate(p):
            p["projects"][0]["project_id"] = "proj-42"
        outcome = _validate(mutate)
        self.assertEqual(outcome.status, validators.REJECTED)
        self.assertIn("unknown_entry_id", _codes(outcome))


class ChangedFactTests(SimpleTestCase):
    """Facts the model altered rather than invented."""

    def test_changed_employment_date_is_rejected(self):
        def mutate(p):
            p["experience"][0]["tailored_bullets"] = [
                "Cut p99 latency by 40% across the platform since 2015."
            ]
        outcome = _validate(mutate)
        self.assertEqual(outcome.status, validators.REJECTED)
        self.assertIn("changed_date", _codes(outcome))

    def test_changed_month_date_is_rejected(self):
        def mutate(p):
            p["experience"][0]["tailored_bullets"] = [
                "Joined the platform team in Jan 2019 and shipped the service."
            ]
        outcome = _validate(mutate)
        self.assertEqual(outcome.status, validators.REJECTED)
        self.assertIn("changed_date", _codes(outcome))

    def test_changed_company_warns_but_does_not_reject(self):
        """An unknown proper noun cannot be decided deterministically."""
        def mutate(p):
            p["experience"][0]["tailored_bullets"] = [
                "Cut p99 latency by 40% across the platform at Initech."
            ]
        outcome = _validate(mutate)
        self.assertEqual(outcome.status, validators.WARNING)
        self.assertIn("unknown_name", _codes(outcome))
        self.assertTrue(outcome.needs_review)

    def test_changed_education_warns(self):
        def mutate(p):
            p["experience"][0]["tailored_bullets"] = [
                "Cut p99 latency by 40% across the platform. MBA, INSEAD."
            ]
        outcome = _validate(mutate)
        self.assertEqual(outcome.status, validators.WARNING)
        self.assertIn("changed_education", _codes(outcome))

    def test_metric_from_another_entry_warns(self):
        """3,000 belongs to the project, not the role: misattribution, not invention."""
        def mutate(p):
            p["experience"][0]["tailored_bullets"] = [
                "Cut p99 latency by 40% while handling 3,000 requests a day."
            ]
        outcome = _validate(mutate)
        self.assertEqual(outcome.status, validators.WARNING)
        self.assertIn("metric_moved_between_entries", _codes(outcome))

    def test_original_mismatch_warns(self):
        def mutate(p):
            p["experience"][0]["original_bullets"] = ["Something the model invented."]
        outcome = _validate(mutate)
        self.assertEqual(outcome.status, validators.WARNING)
        self.assertIn("original_mismatch", _codes(outcome))

    def test_number_formatting_variation_is_not_a_fabrication(self):
        """3,000 in the source, 3000 in the rewrite: same claim."""
        def mutate(p):
            p["projects"][0]["tailored_bullets"] = [
                "Parsed 3000 PDF resumes and extracted structured profiles."
            ]
        outcome = _validate(mutate)
        self.assertEqual(outcome.status, validators.VALID, outcome.as_dict())


class RejectionPolicyTests(SimpleTestCase):
    """
    What ``ResumeTailor`` does with each verdict.

    rejected -> raise, so nothing fabricated ever reaches the user as a suggestion.
    warning  -> return, so the user can review and decide.
    """

    def test_rejected_result_raises_with_violations(self):
        def mutate(p):
            p["experience"][0]["tailored_bullets"] = [
                "Cut p99 latency by 95% across the platform."
            ]
        with self.assertRaises(AITailoringValidationError) as ctx:
            _tailor(mutate)
        self.assertTrue(ctx.exception.violations)
        self.assertIn("fabricated_metric", {v["code"] for v in ctx.exception.violations})

    def test_warning_result_is_returned_for_review(self):
        def mutate(p):
            p["experience"][0]["tailored_bullets"] = [
                "Cut p99 latency by 40% across the platform at Initech."
            ]
        outcome = _tailor(mutate)
        self.assertEqual(outcome.validation.status, validators.WARNING)
        self.assertTrue(outcome.validation.needs_review)

    def test_error_carries_operator_detail_not_user_text(self):
        with self.assertRaises(AITailoringValidationError) as ctx:
            _tailor(lambda p: p["experience"][0].__setitem__("experience_id", "nope"))
        self.assertIn("rejected codes", ctx.exception.detail)
        self.assertNotIn("Initech", ctx.exception.detail)


class ProviderConfigurationTests(SimpleTestCase):
    """``AI_PROVIDER`` selection, including the misconfigured cases."""

    @override_settings(AI_PROVIDER="fake")
    def test_fake_provider_resolves(self):
        self.assertEqual(factory.get_ai_provider().name, "fake")

    @override_settings(AI_PROVIDER="fake")
    def test_describe_provider_omits_secrets(self):
        described = factory.describe_provider()
        self.assertTrue(described["available"])
        self.assertNotIn("base_url", described)
        self.assertNotIn("api_key", described)

    @override_settings(AI_PROVIDER="does-not-exist")
    def test_unknown_provider_raises_configuration_error(self):
        with self.assertRaises(AIConfigurationError):
            factory.get_ai_provider()

    @override_settings(AI_PROVIDER="")
    def test_empty_provider_raises_configuration_error(self):
        with self.assertRaises(AIConfigurationError):
            factory.get_ai_provider()

    @override_settings(AI_PROVIDER="")
    def test_unconfigured_describe_is_reported_not_raised(self):
        described = factory.describe_provider()
        self.assertFalse(described["available"])
        self.assertIn("ollama", described["registered"])

    @override_settings(AI_PROVIDER="does-not-exist")
    def test_service_surfaces_configuration_error(self):
        with self.assertRaises(AIConfigurationError):
            ResumeTailor.tailor_resume(SOURCE_PROFILE, JOB, MATCH)

    def test_ollama_is_registered_but_needs_no_running_daemon(self):
        """Construction must not require a live Ollama to be reachable."""
        self.assertIn("ollama", factory.available_providers())


class ProviderIndependenceTests(SimpleTestCase):
    """
    ``ResumeTailor`` must work with any ``AIProvider`` implementation.

    This is the property that lets a new backend be added without editing the
    service, so it is asserted rather than assumed.
    """

    def test_service_runs_with_an_injected_custom_provider(self):
        class RecordingProvider(FakeAIProvider):
            name = "recording"

            def __init__(self):
                super().__init__(response=json.dumps(valid_payload()))
                self.seen = None

            def tailor_resume(self, request):
                self.seen = request
                return super().tailor_resume(request)

        provider = RecordingProvider()
        outcome = ResumeTailor.tailor_resume(
            SOURCE_PROFILE, JOB, MATCH, jd_profile=JD_PROFILE, provider=provider
        )

        self.assertEqual(outcome.validation.status, validators.VALID)
        # The provider received structured, ID-bearing input it can echo back.
        self.assertEqual(provider.seen.resume["experience"][0]["id"], "exp-0")
        self.assertEqual(provider.seen.job["title"], JOB["title"])
        self.assertEqual(provider.seen.match["score"], MATCH["score"])

    def test_source_dict_is_json_serialisable(self):
        """A provider that is not Ollama may be a hosted API; keep it JSON-safe."""
        import json as _json
        payload = build_source_resume(SOURCE_PROFILE)
        self.assertIsInstance(_json.dumps(payload), str)
