"""
Google Gemini (AI Studio) provider.

Talks to the Generative Language REST API directly with ``requests`` rather than
pulling in the ``google-genai`` SDK. The surface actually used here is one POST
to ``generateContent``, and going direct keeps the dependency list short.

This is the provider for a **hosted** deployment: Render and similar hosts
cannot run an Ollama daemon, so ``AI_PROVIDER=gemini`` is what makes tailoring
work there. Local development still uses ``AI_PROVIDER=ollama``.

Configuration (environment only; nothing is hardcoded):

    AI_PROVIDER=gemini
    GEMINI_API_KEY=...            # server-wide key
    GEMINI_MODEL=gemini-2.0-flash # optional, this is the default

A user who brings their own key has it attached to the request by
``apps.ai.credentials``; it is never logged and never leaves this module.
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings

from apps.ai.exceptions import (
    AIProviderTimeoutError,
    AIProviderUnavailableError,
)

from ..prompts import build_tailoring_prompt
from .base import AIProvider

logger = logging.getLogger(__name__)

API_ROOT = "https://generativelanguage.googleapis.com/v1beta"

#: Cheap, fast, and good enough for rewrite-shaped work. A default, not a
#: requirement: it is a setting and can be overridden.
DEFAULT_MODEL = "gemini-2.0-flash"

#: Gemini is asked for JSON by schema as well as in the prompt, because the
#: model is far more reliable when both agree. schemas.py still parses
#: defensively: a model that returns fences is not worth crashing over.
SYSTEM_PROMPT = (
    "You are a resume tailoring assistant. You rewrite resume bullet points so "
    "they are relevant to a specific job description while remaining strictly "
    "factually accurate. You never invent experience, employers, dates, "
    "technologies, metrics, or education. You always answer with a single JSON "
    "object and no surrounding prose or code fences."
)


class GeminiProvider(AIProvider):
    """Talks to Google Gemini over the Generative Language REST API."""

    name = "gemini"
    display_name = "Google Gemini"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
        temperature: float | None = None,
    ):
        self.api_key = (api_key or getattr(settings, "GEMINI_API_KEY", "") or "").strip()
        self.model = (
            model or getattr(settings, "GEMINI_MODEL", "") or DEFAULT_MODEL
        ).strip()
        self.timeout = timeout or getattr(settings, "GEMINI_TIMEOUT", 120)
        self.temperature = (
            temperature
            if temperature is not None
            else getattr(settings, "GEMINI_TEMPERATURE", 0.2)
        )

    def _key_for(self, request) -> str:
        """A per-user key wins over the deployment-wide one.

        This is the whole bring-your-own-key mechanism: the credential rides
        on the request, is used for that one call, and is never written to a
        log or included in an error detail.
        """
        user_key = (getattr(request, "api_key", "") or "").strip()
        return user_key or self.api_key

    @staticmethod
    def _extract_content(response) -> str:
        """Pull the text out of a ``generateContent`` response.

        Gemini returns content as a list of parts; only the ``text`` parts
        matter, and there is more than one when the model splits its answer.
        """
        try:
            payload = response.json()
        except ValueError as exc:
            raise AIProviderUnavailableError(
                "The AI provider returned an unreadable response.",
                detail=f"generateContent returned non-JSON: {exc}",
            ) from exc

        parts: list[str] = []
        for candidate in payload.get("candidates") or []:
            content = candidate.get("content") or {}
            for part in content.get("parts") or []:
                if part.get("text"):
                    parts.append(part["text"])

        if parts:
            return "".join(parts)

        # A 200 with no text is almost always a safety block, and it is worth
        # saying so rather than letting an empty string become "no changes".
        blocked = (payload.get("promptFeedback") or {}).get("blockReason")
        if blocked:
            raise AIProviderUnavailableError(
                "The AI provider declined to answer for this content.",
                detail=f"promptFeedback.blockReason={blocked!r}",
            )

        raise AIProviderUnavailableError(
            "The AI provider returned an empty response.",
            detail=f"no text parts in response: {str(payload)[:400]}",
        )

    def tailor_resume(self, request) -> str:
        key = self._key_for(request)
        if not key:
            raise AIProviderUnavailableError(
                "No Gemini API key is configured. Add one in Settings, or set "
                "GEMINI_API_KEY on the server.",
                detail="neither a per-user key nor GEMINI_API_KEY is set",
            )

        body = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [
                {"role": "user", "parts": [{"text": build_tailoring_prompt(request)}]}
            ],
            "generationConfig": {
                "temperature": self.temperature,
                "responseMimeType": "application/json",
            },
        }

        url = f"{API_ROOT}/models/{self.model}:generateContent"
        logger.info(
            "ai.provider_request provider=gemini model=%s user_key=%s",
            self.model,
            "yes" if (getattr(request, "api_key", "") or "").strip() else "no",
        )

        try:
            response = requests.post(
                url,
                json=body,
                timeout=self.timeout,
                headers={"x-goog-api-key": key},
            )
        except requests.Timeout as exc:
            raise AIProviderTimeoutError(
                "The AI provider took too long to respond. Please try again.",
                detail=f"POST {url} timed out after {self.timeout}s: {exc}",
            ) from exc
        except requests.RequestException as exc:
            raise AIProviderUnavailableError(
                "The AI provider is not available. Please try again later.",
                detail=f"POST {url} failed: {exc}",
            ) from exc

        if response.status_code in (400, 401, 403):
            # Almost always an invalid, wrong-type, or out-of-quota key. The
            # fix is on the user's side, so say that rather than "try later".
            raise AIProviderUnavailableError(
                "Gemini rejected the API key. Check it in Google AI Studio.",
                detail=f"POST {url} returned {response.status_code}: "
                f"{response.text[:400]}",
            )

        if response.status_code == 404:
            raise AIProviderUnavailableError(
                f"The configured AI model '{self.model}' does not exist.",
                detail=f"POST {url} returned 404 for model {self.model!r}",
            )

        if response.status_code == 429:
            raise AIProviderTimeoutError(
                "The AI provider's rate limit was reached. Please try again shortly.",
                detail=f"POST {url} returned 429: {response.text[:400]}",
            )

        if response.status_code >= 400:
            raise AIProviderUnavailableError(
                "The AI provider returned an error. Please try again later.",
                detail=f"POST {url} returned {response.status_code}: "
                f"{response.text[:400]}",
            )

        return self._extract_content(response)

    def health(self) -> tuple[bool, str]:
        """Report whether a key is present.

        A live API call is deliberately not made: this runs on page load from
        ``/tailor/status/``, and the free tier bills per request. It answers
        "is this configured", not "is the provider's uptime good".
        """
        if not self.api_key:
            return False, (
                "No server-wide Gemini key. Users can still add their own key "
                "in Settings."
            )
        return True, f"Gemini ready (model {self.model})"

    def describe(self) -> dict:
        """Non-secret metadata. Never includes the key, or any part of it."""
        return {
            "provider": self.name,
            "display_name": self.display_name,
            "model": self.model,
            # Reported so the client knows a per-user key is the intended path
            # when the server has none.
            "server_key_configured": bool(self.api_key),
        }
