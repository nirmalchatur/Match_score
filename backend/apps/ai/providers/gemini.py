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
    GEMINI_MODEL=gemini-2.0-flash # optional, this is the default
    GEMINI_TIMEOUT=120            # optional

There is deliberately **no** ``GEMINI_API_KEY``. This provider is
bring-your-own-key only: the user's key is stored encrypted in
``apps.users.models.ProviderCredential``, decrypted by the tailoring view, and
attached to the request for the duration of one call. A deployment therefore
never spends the owner's quota on anyone else's behalf, and a leaked server
secret cannot be used to call Gemini.
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
        model: str | None = None,
        timeout: int | None = None,
        temperature: float | None = None,
    ):
        # No api_key parameter and no server-wide key. This provider is
        # bring-your-own-key only: the credential arrives on the request, from
        # the user who typed it into the UI. There is deliberately no fallback
        # to an environment variable, so a deployment can never end up quietly
        # spending the owner's quota on someone else's behalf.
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
        """The user's own key, carried on the request.

        This is the whole bring-your-own-key mechanism: the credential rides on
        the request, is used for that one call, and is never written to a log
        or included in an error detail.
        """
        return (getattr(request, "api_key", "") or "").strip()

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
                "No Google AI Studio API key. Add one in Settings to use "
                "tailoring.",
                detail="the request carried no user api_key",
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
        """Report whether a deployment-level key is configured.

        With bring-your-own-key there is no server key, so this is normally
        ``False`` and the message points at the user's own Settings entry
        rather than at a server variable. ``/tailor/status/`` reports
        availability per signed-in user, not globally, so the wording matters
        more than the boolean.
        """
        return False, (
            "Add your own Google AI Studio API key in Settings to enable "
            "tailoring."
        )

    def describe(self) -> dict:
        """Non-secret metadata. Never includes a key, or any part of one."""
        return {
            "provider": self.name,
            "display_name": self.display_name,
            "model": self.model,
            # Always False: this provider has no server-side key by design.
            "server_key_configured": False,
            "requires_user_key": True,
        }
