"""
Groq provider (hosted, OpenAI-compatible).

The second hosted backend. It exists for two reasons worth stating, because
"add a provider" is otherwise a change with no justification:

1. **Speed.** For rewrite-shaped work -- rewrite bullets, keep the facts -- a
   small hosted model on Groq's LPU returns in seconds where a free-tier Gemini
   request can sit for a minute. Tailoring feels like a dead UI for that minute.
2. **Independence.** Gemini and Groq fail differently: Google retires models on
   its own schedule (the 2.0 Flash retirement broke every user of this app at
   once), Groq rate limits per-account. Having both means a bad day for one
   vendor is a configuration change rather than an outage.

Wire format is OpenAI's ``/openai/v1/chat/completions``, so this is a direct
``requests`` POST for the same reason the Gemini provider is: the surface used
here is one endpoint, and an SDK would be a large dependency for it.

Configuration (environment only; nothing hardcoded):

    AI_PROVIDER=groq
    GROQ_API_KEY=gsk_...            # optional deployment fallback
    GROQ_MODEL=llama-3.3-70b-versatile
    GROQ_TIMEOUT=120

Like Gemini, a key may come from the request (the user's own, stored encrypted)
or from the environment. Which one is decided in
:mod:`apps.ai.selection.resolve_api_key`, not here -- this provider only ever
sees a key that already exists and treats it as opaque.
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings

from apps.ai.exceptions import (
    AIProviderResponseError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
)

from ..prompts import build_tailoring_prompt
from .base import AIProvider

logger = logging.getLogger(__name__)

API_ROOT = "https://api.groq.com/openai/v1"

#: The default Groq model. ``GROQ_MODEL`` overrides it.
#:
#: Groq does not follow a published retirement calendar the way Google does, so
#: unlike the Gemini provider there is no fallback list: a retired model here is
#: a deployment setting that should be changed deliberately, and silently
#: swapping a user's chosen model would be the wrong kind of helpful.
DEFAULT_MODEL = "llama-3.3-70b-versatile"

#: Identical to Gemini's. Stated here rather than imported so each provider file
#: reads on its own; they are two separate contracts that happen to agree today.
SYSTEM_PROMPT = (
    "You are a resume tailoring assistant. You rewrite resume bullet points so "
    "they are relevant to a specific job description while remaining strictly "
    "factually accurate. You never invent experience, employers, dates, "
    "technologies, metrics, or education. You always answer with a single JSON "
    "object and no surrounding prose or code fences."
)


class GroqProvider(AIProvider):
    """Talks to Groq's OpenAI-compatible chat completions endpoint."""

    name = "groq"
    display_name = "Groq"

    def __init__(
        self,
        model: str | None = None,
        timeout: int | None = None,
        temperature: float | None = None,
    ):
        self.model = (
            model or getattr(settings, "GROQ_MODEL", "") or DEFAULT_MODEL
        ).strip()
        self.timeout = timeout or getattr(settings, "GROQ_TIMEOUT", 120)
        self.temperature = (
            temperature
            if temperature is not None
            else getattr(settings, "GROQ_TEMPERATURE", 0.2)
        )

    def _key_for(self, request) -> str:
        """
        The key to use, carried on the request.

        Resolution already happened upstream
        (:func:`apps.ai.selection.resolve_api_key`): user key first, then the
        deployment env key, then empty. This method only normalises, so a
        whitespace-only value is treated as absent rather than sent as a header
        that will 401.
        """
        return (getattr(request, "api_key", "") or "").strip()
        return (getattr(request, "api_key", "") or "").strip()

    def _post(self, body: dict, key: str):
        """One chat-completions call, with transport errors translated."""
        url = f"{API_ROOT}/chat/completions"
        try:
            return requests.post(
                url,
                json=body,
                timeout=self.timeout,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
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

    @staticmethod
    def _extract_content(response) -> str:
        """
        Pull the assistant text out of an OpenAI-shaped response.

        Deliberately tolerant: a model that answers with a code fence, or that
        returns only ``reasoning_content``, would otherwise reach the schema
        parser as something it has to survive.
        """
        try:
            payload = response.json()
        except ValueError as exc:
            raise AIProviderResponseError(
                "The AI provider returned an unreadable response.",
                detail=f"chat/completions returned non-JSON: {exc}",
            ) from exc

        choices = payload.get("choices") or []
        if not choices:
            raise AIProviderResponseError(
                "The AI provider returned an empty response.",
                detail=f"no choices in response: {str(payload)[:400]}",
            )

        message = choices[0].get("message") or {}
        content = message.get("content")

        if not isinstance(content, str) or not content.strip():
            # finish_reason="length" means the model ran out of budget mid-JSON.
            # Saying so is the difference between "try again" and "your provider
            # is misconfigured", which are very different instructions.
            if choices[0].get("finish_reason") == "length":
                raise AIProviderResponseError(
                    "The AI provider's answer was cut off before it finished. "
                    "Please try again.",
                    detail="finish_reason=length",
                )
            raise AIProviderResponseError(
                "The AI provider returned an empty response.",
                detail=f"message keys returned: {sorted(message.keys())}",
            )

        return content

    def tailor_resume(self, request) -> str:
        key = self._key_for(request)
        if not key:
            raise AIProviderUnavailableError(
                "No Groq API key. Add one in Settings to use tailoring.",
                detail="the request carried no api_key",
            )

        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_tailoring_prompt(request)},
            ],
            # Low temperature by default: this task must stay close to the
            # source text rather than improvise, which is the same reasoning
            # the Ollama and Gemini providers use.
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
        }

        response = self._post(body, key)
        url = f"{API_ROOT}/chat/completions"

        if response.status_code in (401, 403):
            raise AIProviderUnavailableError(
                "Groq rejected the API key. Check it in the Groq console.",
                detail=f"POST {url} returned {response.status_code}: "
                f"{response.text[:400]}",
            )

        if response.status_code == 404:
            # Groq 404s an unknown model and an unknown key on some plans, so
            # the message names the model as the thing to check rather than
            # claiming to know which of the two it actually was.
            raise AIProviderUnavailableError(
                "This deployment is pointing at a model Groq does not serve. "
                "Please contact the app owner.",
                detail=f"POST {url} returned 404 for model {self.model!r}",
            )

        if response.status_code == 429:
            raise AIProviderTimeoutError(
                "The AI provider's rate limit was reached. Please try again "
                "shortly.",
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
        """
        Report whether a key is available from *some* source.

        Unlike the old Gemini behaviour this returns True when the deployment
        holds a key, because in that case tailoring genuinely works. The
        per-user status endpoint does not use this for the button's enabled
        state; it exists for the Settings diagnostics panel.
        """
        from apps.ai.selection import has_deployment_key

        if has_deployment_key(self.name):
            return True, "A deployment-level Groq key is configured."
        return False, (
            "Add your own Groq API key in Settings to enable tailoring."
        )

    def describe(self) -> dict:
        """Non-secret metadata. Never includes a key, or any part of one."""
        from apps.ai.selection import has_deployment_key

        configured = has_deployment_key(self.name)
        return {
            "provider": self.name,
            "display_name": self.display_name,
            "model": self.model,
            # True when the deployment can pay for calls on a user's behalf.
            # Reported so the UI can say "using the app's key" rather than
            # prompting someone to paste one they do not need to.
            "server_key_configured": configured,
            "requires_user_key": not configured,
        }