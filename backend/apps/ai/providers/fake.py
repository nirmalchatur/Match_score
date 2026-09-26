"""
Deterministic test double for :class:`~apps.ai.providers.base.AIProvider`.

This is a **test** utility, not a product feature: it never talks to a network
and never invents a "pretend" hosted provider. It exists so the test suite can
exercise the full tailoring pipeline — success, malformed output, hallucinated
skills, invented metrics, provider errors — without requiring a running Ollama
instance, keeping CI free and hermetic.

It is registered in the factory under the name ``fake`` so tests can select it
with ``AI_PROVIDER=fake`` or by patching ``get_ai_provider``.
"""

from __future__ import annotations

import json

from apps.ai.exceptions import (
    AIProviderResponseError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
)
from apps.ai.providers.base import AIProvider, TailoringRequest


class FakeAIProvider(AIProvider):
    """Returns a canned, well-formed tailoring document."""

    name = "fake"
    display_name = "Fake provider (tests only)"

    #: Raw text returned when no scenario is configured. Valid JSON.
    default_response: str = json.dumps(
        {
            "summary": {
                "original": "",
                "tailored": "Backend engineer with experience in the source resume.",
                "reason": "Aligns the opening with the target role.",
            },
            "experience": [],
            "projects": [],
            "skills": {
                "emphasized": [],
                "deemphasized": [],
                "unsupported_requirements": [],
            },
            "warnings": [],
        }
    )

    def __init__(self, response: str | None = None, error: Exception | None = None):
        #: Override the raw body to test parsing/validation paths.
        self.response = response if response is not None else self.default_response
        #: Raise this instead of responding, to test provider failure paths.
        self.error = error
        #: Requests seen by this provider, for assertions.
        self.calls: list[TailoringRequest] = []

    def tailor_resume(self, request: TailoringRequest) -> str:
        self.calls.append(request)

        if isinstance(self.error, AIProviderTimeoutError):
            raise self.error
        if isinstance(self.error, AIProviderUnavailableError):
            raise self.error
        if isinstance(self.error, AIProviderResponseError):
            raise self.error
        if self.error is not None:
            raise self.error

        return self.response

    # Convenience constructors for common test scenarios -----------------

    @classmethod
    def returning(cls, payload: dict | str) -> "FakeAIProvider":
        """A provider that replies with the given dict (or raw string)."""
        body = payload if isinstance(payload, str) else json.dumps(payload)
        return cls(response=body)

    @classmethod
    def malformed(cls) -> "FakeAIProvider":
        """A provider that replies with something that is not JSON."""
        return cls(response="Sure! Here is your tailored resume: (not json)")

    @classmethod
    def unavailable(cls) -> "FakeAIProvider":
        """A provider that simulates an unreachable backend."""
        return cls(
            error=AIProviderUnavailableError(
                "The AI provider is not available. Please try again later."
            )
        )

    @classmethod
    def timing_out(cls) -> "FakeAIProvider":
        """A provider that simulates a timeout."""
        return cls(
            error=AIProviderTimeoutError(
                "The AI provider took too long to respond. Please try again."
            )
        )

    def health(self) -> tuple[bool, str]:
        return True, "Fake provider ready"
