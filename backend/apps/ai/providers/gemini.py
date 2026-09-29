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
    GEMINI_MODEL=gemini-3.8-flash # optional, this is the default
    GEMINI_TIMEOUT=120            # optional
    GEMINI_API_KEY=...            # optional deployment fallback

Key resolution lives in :func:`apps.ai.selection.resolve_api_key`: the user's
own stored key wins, and the deployment's ``GEMINI_API_KEY`` is used only when
the user has none. That indirection is why this provider takes a plain string
on the request and never reads an environment variable itself -- the choice of
source belongs to one module, not to each provider.
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
#:
#: Google shuts models down on a schedule, and a shut-down model answers 404
#: for every key. The previous default, gemini-2.0-flash, was shut down in June
#: 2026, which broke every user of this app at once. Note that gemini-2.5-flash
#: is *not* a safe substitute even though it is not formally deprecated: Google
#: limits 2.5-series access to keys that have used them before, so a freshly
#: created bring-your-own key gets refused. Their guidance for new projects is
#: the 3.x Flash line, which is what this uses.
DEFAULT_MODEL = "gemini-3.8-flash"

#: Tried in order when the configured model is gone. A retirement is a Google
#: schedule, not something a user can fix, so the call is retried on a model
#: that is current rather than failing the user's tailoring outright.
FALLBACK_MODELS = ("gemini-3.7-flash", "gemini-3.6-flash")

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
        # No api_key parameter and no environment read. The credential arrives
        # already resolved on the request, from the user who typed it into the
        # UI or from the deployment fallback -- decide that in
        # apps.ai.selection, not here, so every provider agrees on precedence.
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
        """
        The key resolved for this call, carried on the request.

        Whichever source it came from -- the user's own stored credential or
        the deployment's env fallback -- it is used for exactly one call, never
        written to a log, and never included in an error detail.
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

    def _post(self, model: str, body: dict, key: str):
        """One ``generateContent`` call, with transport errors translated."""
        url = f"{API_ROOT}/models/{model}:generateContent"
        try:
            return requests.post(
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

    def tailor_resume(self, request) -> str:
        key = self._key_for(request)
        if not key:
            # Reached only when neither the user nor the deployment has a key,
            # because resolve_api_key() would otherwise have supplied one. The
            # message therefore points only at the user-facing action.
            raise AIProviderUnavailableError(
                "No Google AI Studio API key. Add one in Settings to use "
                "tailoring.",
                detail="no user credential and no GEMINI_API_KEY on the server",
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

        tried: list[str] = []
        used = self.model
        for model in (self.model, DEFAULT_MODEL, *FALLBACK_MODELS):
            if model in tried:
                continue
            tried.append(model)
            response = self._post(model, body, key)
            used = model
            if response.status_code != 404:
                break
            # A 404 here means the model is gone, never that the key is bad:
            # Google authenticates before it resolves the model, so an invalid
            # key is a 400/401/403 and is handled below without any fallback.
            logger.warning(
                "ai.model_retired provider=gemini model=%s; trying the next one",
                model,
            )

        url = f"{API_ROOT}/models/{used}:generateContent"
        logger.info(
            "ai.provider_request provider=gemini model=%s user_key=%s",
            used,
            "yes" if (getattr(request, "api_key", "") or "").strip() else "no",
        )

        if response.status_code == 400:
            # A 400 is INVALID_ARGUMENT about the *request*, not the key. The
            # common cause on Gemini 3.x is sampling parameters: Google dropped
            # temperature/top_p/top_k in the 3 migration and answers a bare
            # "Request contains an invalid argument" for them. Retry once with
            # the bare minimum before giving up, so a model that dislikes
            # `temperature` does not take the whole feature down with it.
            minimal = dict(body)
            minimal["generationConfig"] = {"responseMimeType": "application/json"}
            logger.warning(
                "ai.generation_config_rejected provider=gemini model=%s; "
                "retrying without sampling parameters",
                used,
            )
            retry = self._post(used, minimal, key)
            if retry.status_code == 200:
                return self._extract_content(retry)
            if retry.status_code in (401, 403):
                response = retry
            else:
                raise AIProviderUnavailableError(
                    "Gemini rejected the request as invalid. Your API key is "
                    "fine; this is a server-side configuration problem. Please "
                    "contact the app owner.",
                    detail=f"POST {url} returned 400, and still "
                    f"{retry.status_code} without sampling parameters: "
                    f"{response.text[:300]} / {retry.text[:300]}",
                )

        if response.status_code in (401, 403):
            # Genuinely the user's key: invalid, wrong-type, or out of quota.
            # The fix is on their side, so say that rather than "try later".
            raise AIProviderUnavailableError(
                "Gemini rejected the API key. Check it in Google AI Studio.",
                detail=f"POST {url} returned {response.status_code}: "
                f"{response.text[:400]}",
            )

        if response.status_code == 404:
            # Every configured and fallback model has been retired. This says
            # what it is -- a server-side model problem, nothing to do with the
            # user's key -- because the old wording ("does not exist") sent
            # people to Google AI Studio to re-check a perfectly good key.
            raise AIProviderUnavailableError(
                "This deployment is pointing at an AI model that Google has "
                "retired. Your API key is fine. Please contact the app owner.",
                detail=f"POST {url} returned 404 for model {used!r}; "
                f"tried {tried!r}",
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
        """
        Report whether a key is available from *some* source.

        True when the deployment set ``GEMINI_API_KEY``, because in that case
        tailoring genuinely works for every user. ``/tailor/status/`` reports
        availability per signed-in user and does not consult this for the
        button's state, but Settings does, and returning a hard False here
        would tell an operator their working deployment was broken.
        """
        from apps.ai.selection import has_deployment_key

        if has_deployment_key(self.name):
            return True, "A deployment-level Google AI Studio key is configured."
        return False, (
            "Add your own Google AI Studio API key in Settings to enable "
            "tailoring."
        )

    def describe(self) -> dict:
        """Non-secret metadata. Never includes a key, or any part of one."""
        from apps.ai.selection import has_deployment_key

        configured = has_deployment_key(self.name)
        return {
            "provider": self.name,
            "display_name": self.display_name,
            "model": self.model,
            # Whether the deployment can pay on a user's behalf. The UI uses
            # this to say "using the app's key" instead of asking for one the
            # user does not actually need to supply.
            "server_key_configured": configured,
            "requires_user_key": not configured,
        }
