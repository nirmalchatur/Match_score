"""
Gemini transport contract, with emphasis on the model-retirement path.

This module did not exist until gemini-2.0-flash was shut down by Google in
June 2026, which made every user of this app fail at once with "The configured
AI model 'gemini-2.0-flash' does not exist." No test had ever exercised the
Gemini provider's status-code handling, so nothing noticed.

The distinction that caused the confusion, and which the code relies on:

* **404** -- the model is gone. The key authenticated fine; Google resolves the
  model only after checking the key. Recoverable, so the provider falls back.
* **400/401/403** -- the key is the problem. Retrying with another model would
  just fail again, so no fallback is attempted.

Requests are stubbed. Nothing here proves a real Gemini key round-trips; that is
a manual check (see docs/AI_SETUP.md).
"""

import json
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.ai.exceptions import AIProviderTimeoutError, AIProviderUnavailableError
from apps.ai.providers.base import TailoringRequest
from apps.ai.providers.gemini import (
    DEFAULT_MODEL,
    FALLBACK_MODELS,
    GeminiProvider,
)

from .fixtures import JOB, SOURCE_BULLETS, SOURCE_PROFILE, valid_payload


def _request(api_key: str = "test-key") -> TailoringRequest:
    return TailoringRequest(
        resume=SOURCE_PROFILE,
        job=JOB,
        match={"score": 82.5, "decision": "TAILOR"},
        api_key=api_key,
    )


class _Response:
    """The slice of a ``requests`` response this provider actually reads."""

    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload or {})

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def _ok() -> _Response:
    return _Response(
        200,
        {"candidates": [{"content": {"parts": [{"text": json.dumps(valid_payload())}]}}]},
    )


def _retired() -> _Response:
    return _Response(404, {"error": {"code": 404, "message": "models/x is not found"}})


def _model_of(url: str) -> str:
    return url.split("/models/")[1].split(":")[0]
class GeminiRetiredModelTests(SimpleTestCase):
    def test_retired_configured_model_falls_back_and_succeeds(self):
        """The regression that broke every user: a 404 must not end the call."""
        calls: list[str] = []

        def fake_post(url, **kwargs):
            calls.append(_model_of(url))
            return _retired() if _model_of(url) == "gemini-2.0-flash" else _ok()

        with patch("apps.ai.providers.gemini.requests.post", side_effect=fake_post):
            out = GeminiProvider(model="gemini-2.0-flash").tailor_resume(_request())

        self.assertEqual(json.loads(out), valid_payload())
        self.assertEqual(calls, ["gemini-2.0-flash", DEFAULT_MODEL])

    def test_exhausts_every_candidate_before_giving_up(self):
        """All retired -> one clear error, and each model tried exactly once."""
        calls: list[str] = []

        def fake_post(url, **kwargs):
            calls.append(_model_of(url))
            return _retired()

        with patch("apps.ai.providers.gemini.requests.post", side_effect=fake_post):
            with self.assertRaises(AIProviderUnavailableError) as ctx:
                GeminiProvider(model="gemini-2.0-flash").tailor_resume(_request())

        self.assertEqual(len(calls), len(set(calls)), "a model was retried")
        expected = ["gemini-2.0-flash", DEFAULT_MODEL, *FALLBACK_MODELS]
        self.assertEqual(calls, expected[: len(calls)])
        self.assertIn("Your API key is fine", str(ctx.exception))

    def test_no_duplicate_request_when_configured_model_is_the_default(self):
        """If the setting already equals DEFAULT_MODEL it is tried once."""
        calls: list[str] = []

        def fake_post(url, **kwargs):
            calls.append(_model_of(url))
            return _ok()

        with patch("apps.ai.providers.gemini.requests.post", side_effect=fake_post):
            GeminiProvider(model=DEFAULT_MODEL).tailor_resume(_request())

        self.assertEqual(calls, [DEFAULT_MODEL])


class GeminiKeyRejectionTests(SimpleTestCase):
    """A bad key is the user's to fix. Retrying models would only delay that."""

    def test_rejected_key_is_never_retried_across_models(self):
        for code in (401, 403):
            with self.subTest(code=code):
                calls: list[str] = []

                def fake_post(url, **kwargs):
                    calls.append(url)
                    return _Response(code, {"error": {"message": "bad key"}})

                with patch("apps.ai.providers.gemini.requests.post", side_effect=fake_post):
                    with self.assertRaises(AIProviderUnavailableError) as ctx:
                        GeminiProvider(model="gemini-2.0-flash").tailor_resume(_request())

                self.assertEqual(len(calls), 1, "a rejected key must not be retried")
                self.assertIn("API key", str(ctx.exception))


class GeminiBadRequestTests(SimpleTestCase):
    """
    A 400 is about the request, not the key.

    Gemini 3.x rejects sampling parameters, so the provider retries once with a
    minimal generationConfig. Crucially, a 400 must never be reported as a bad
    key: that is what sent people to re-check a perfectly good key.
    """

    def test_400_retries_without_temperature_then_succeeds(self):
        seen: list[dict] = []

        def fake_post(url, **kwargs):
            config = kwargs["json"]["generationConfig"]
            seen.append(config)
            if "temperature" in config:
                return _Response(400, {"error": {"message": "invalid argument"}})
            return _ok()

        with patch("apps.ai.providers.gemini.requests.post", side_effect=fake_post):
            out = GeminiProvider().tailor_resume(_request())

        self.assertEqual(json.loads(out), valid_payload())
        self.assertEqual(len(seen), 2)
        self.assertIn("temperature", seen[0])
        self.assertNotIn("temperature", seen[1])
        # JSON mode must survive the retry, or the parser gets prose.
        self.assertEqual(seen[1]["responseMimeType"], "application/json")

    def test_persistent_400_does_not_blame_the_user_key(self):
        def fake_post(url, **kwargs):
            return _Response(400, {"error": {"message": "invalid argument"}})

        with patch("apps.ai.providers.gemini.requests.post", side_effect=fake_post):
            with self.assertRaises(AIProviderUnavailableError) as ctx:
                GeminiProvider().tailor_resume(_request())

        self.assertNotIn("Gemini rejected the API key", str(ctx.exception))
        self.assertIn("Your API key is fine", str(ctx.exception))

    def test_a_400_that_is_really_the_key_is_still_reported_as_such(self):
        """If the stripped retry comes back 403, the key really is the problem."""
        codes = iter([400, 403])

        def fake_post(url, **kwargs):
            return _Response(next(codes), {"error": {"message": "no"}})

        with patch("apps.ai.providers.gemini.requests.post", side_effect=fake_post):
            with self.assertRaises(AIProviderUnavailableError) as ctx:
                GeminiProvider().tailor_resume(_request())

        self.assertIn("Gemini rejected the API key", str(ctx.exception))


class GeminiDefaultModelTests(SimpleTestCase):
    def test_default_is_not_a_retired_model(self):
        """Google retired gemini-2.0-flash in June 2026; do not ship it again."""
        self.assertNotIn(DEFAULT_MODEL, ("gemini-2.0-flash", "gemini-2.0-flash-lite"))
        self.assertTrue(DEFAULT_MODEL.startswith("gemini-3"))

    def test_every_fallback_is_a_distinct_live_candidate(self):
        for model in (*FALLBACK_MODELS, DEFAULT_MODEL):
            with self.subTest(model=model):
                self.assertTrue(model.startswith("gemini-3"))
        self.assertEqual(len(set(FALLBACK_MODELS)), len(FALLBACK_MODELS))

    @override_settings(GEMINI_MODEL="")
    def test_absent_setting_uses_the_default(self):
        self.assertEqual(GeminiProvider().model, DEFAULT_MODEL)

    def test_429_is_a_rate_limit_not_a_model_problem(self):
        with patch(
            "apps.ai.providers.gemini.requests.post",
            return_value=_Response(429, {"error": {"message": "slow down"}}),
        ):
            with self.assertRaises(AIProviderTimeoutError):
                GeminiProvider().tailor_resume(_request())

    def test_missing_key_fails_before_any_network_call(self):
        with patch("apps.ai.providers.gemini.requests.post") as post:
            with self.assertRaises(AIProviderUnavailableError) as ctx:
                GeminiProvider().tailor_resume(_request(api_key=""))
        post.assert_not_called()
        self.assertIn("No Google AI Studio API key", str(ctx.exception))


class GeminiRequestShapeTests(SimpleTestCase):
    def test_key_travels_in_the_header_never_in_the_body(self):
        """A user's key must not be serialised into a prompt or a log line."""
        seen: dict = {}

        def fake_post(url, **kwargs):
            seen.update(kwargs)
            seen["url"] = url
            return _ok()

        with patch("apps.ai.providers.gemini.requests.post", side_effect=fake_post):
            GeminiProvider().tailor_resume(_request(api_key="secret-key-123"))

        self.assertEqual(seen["headers"]["x-goog-api-key"], "secret-key-123")
        self.assertNotIn("secret-key-123", json.dumps(seen["json"]))
        self.assertIn("models/", seen["url"])

    def test_asks_for_json_so_the_parser_receives_an_object(self):
        seen: dict = {}

        def fake_post(url, **kwargs):
            seen.update(kwargs)
            return _ok()

        with patch("apps.ai.providers.gemini.requests.post", side_effect=fake_post):
            GeminiProvider().tailor_resume(_request())

        self.assertEqual(
            seen["json"]["generationConfig"]["responseMimeType"], "application/json"
        )

    def test_safety_block_is_named_rather_than_read_as_empty(self):
        blocked = _Response(200, {"promptFeedback": {"blockReason": "SAFETY"}})
        with patch("apps.ai.providers.gemini.requests.post", return_value=blocked):
            with self.assertRaises(AIProviderUnavailableError) as ctx:
                GeminiProvider().tailor_resume(_request())
        self.assertIn("declined", str(ctx.exception))

    def test_bullets_from_the_request_reach_the_prompt(self):
        """Guards against the prompt silently losing the resume content."""
        seen: dict = {}

        def fake_post(url, **kwargs):
            seen.update(kwargs)
            return _ok()

        with patch("apps.ai.providers.gemini.requests.post", side_effect=fake_post):
            GeminiProvider().tailor_resume(_request())

        text = seen["json"]["contents"][0]["parts"][0]["text"]
        self.assertIn(SOURCE_BULLETS[0], text)
