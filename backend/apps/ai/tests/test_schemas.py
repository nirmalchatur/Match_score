"""
Parsing tolerance and provider-failure tests.

These cover the ``apps.ai.schemas`` layer (how a raw model string becomes a
``TailoringResult``) and the error paths of ``apps.ai.providers.fake``. No
Ollama, no network: the whole suite runs on ``FakeAIProvider``.
"""

import json

from django.test import SimpleTestCase

from apps.ai.exceptions import (
    AIProviderResponseError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
)
from apps.ai.providers.base import TailoringRequest
from apps.ai.providers.fake import FakeAIProvider
from apps.ai.schemas import extract_json, parse_tailoring_response
from apps.ai.tailor import ResumeTailor

from .fixtures import JOB, JD_PROFILE, MATCH, SOURCE_PROFILE, valid_payload


def _request() -> TailoringRequest:
    return TailoringRequest(resume={}, job={}, match={})


class ParseToleranceTests(SimpleTestCase):
    """Real models fence, prefix and wrap their JSON. All of that must parse."""

    def test_plain_json_parses(self):
        result = parse_tailoring_response(json.dumps(valid_payload()))
        self.assertEqual(len(result.experience), 1)
        self.assertEqual(result.experience[0].entry_id, "exp-0")

    def test_fenced_json_is_accepted(self):
        raw = "```json\n" + json.dumps(valid_payload()) + "\n```"
        result = parse_tailoring_response(raw)
        self.assertEqual(len(result.experience), 1)

    def test_fence_without_language_tag_is_accepted(self):
        raw = "```\n" + json.dumps(valid_payload()) + "\n```"
        self.assertEqual(len(parse_tailoring_response(raw).experience), 1)

    def test_prose_around_json_is_accepted(self):
        raw = (
            "Sure! Here is the tailored resume you asked for:\n\n"
            + json.dumps(valid_payload())
            + "\n\nLet me know if you want any changes."
        )
        self.assertEqual(len(parse_tailoring_response(raw).experience), 1)

    def test_missing_fields_default_to_empty(self):
        result = parse_tailoring_response("{}")
        self.assertEqual(result.experience, [])
        self.assertEqual(result.projects, [])
        self.assertEqual(result.warnings, [])
        self.assertTrue(result.is_empty)

    def test_summary_only_payload_is_usable(self):
        raw = json.dumps({"summary": {"tailored": "Backend engineer."}})
        result = parse_tailoring_response(raw)
        self.assertEqual(result.summary.tailored, "Backend engineer.")

    def test_entry_without_id_is_dropped(self):
        payload = valid_payload()
        del payload["experience"][0]["experience_id"]
        result = parse_tailoring_response(json.dumps(payload))
        self.assertEqual(result.experience, [], "an entry with no id cannot be traced")

    def test_entry_with_blank_id_is_dropped(self):
        payload = valid_payload()
        payload["experience"][0]["experience_id"] = "   "
        self.assertEqual(parse_tailoring_response(json.dumps(payload)).experience, [])

    def test_malformed_json_raises_provider_response_error(self):
        with self.assertRaises(AIProviderResponseError):
            extract_json("{not json at all")

    def test_empty_response_raises(self):
        with self.assertRaises(AIProviderResponseError):
            extract_json("   ")

    def test_non_object_json_raises(self):
        with self.assertRaises(AIProviderResponseError):
            extract_json("[1, 2, 3]")

    def test_list_instead_of_object_for_section_is_tolerated(self):
        payload = valid_payload()
        payload["experience"] = "not a list"
        self.assertEqual(parse_tailoring_response(json.dumps(payload)).experience, [])


class ProviderFailureTests(SimpleTestCase):
    """Provider errors must reach the caller unchanged, not be swallowed."""

    def test_unavailable_provider_raises(self):
        with self.assertRaises(AIProviderUnavailableError):
            FakeAIProvider.unavailable().tailor_resume(_request())

    def test_timing_out_provider_raises(self):
        with self.assertRaises(AIProviderTimeoutError):
            FakeAIProvider.timing_out().tailor_resume(_request())

    def test_malformed_provider_output_raises(self):
        provider = FakeAIProvider.malformed()
        with self.assertRaises(AIProviderResponseError):
            ResumeTailor.tailor_resume(SOURCE_PROFILE, JOB, MATCH, provider=provider)

    def test_service_propagates_unavailable(self):
        with self.assertRaises(AIProviderUnavailableError):
            ResumeTailor.tailor_resume(
                SOURCE_PROFILE, JOB, MATCH, provider=FakeAIProvider.unavailable()
            )

    def test_service_propagates_timeout(self):
        with self.assertRaises(AIProviderTimeoutError):
            ResumeTailor.tailor_resume(
                SOURCE_PROFILE, JOB, MATCH, provider=FakeAIProvider.timing_out()
            )
