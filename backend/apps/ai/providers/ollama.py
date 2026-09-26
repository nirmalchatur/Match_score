"""
Ollama provider (local, free, open-source friendly).

This is the **only** module in the codebase allowed to know that Ollama exists.
Everything Ollama-specific â€” the ``/api/chat`` endpoint, the ``stream`` flag,
the ``format: json`` option, model naming, the base URL â€” is confined here.

Configuration (all via environment; nothing is hardcoded across the codebase):

    AI_PROVIDER=ollama
    OLLAMA_BASE_URL=http://localhost:11434
    OLLAMA_MODEL=llama3.1
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from django.conf import settings

from apps.ai.exceptions import (
    AIProviderResponseError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
)
from apps.ai.prompts import build_tailoring_prompt
from apps.ai.providers.base import AIProvider, TailoringRequest

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a resume tailoring assistant. You rewrite resume bullet points so "
    "they are relevant to a specific job description while remaining strictly "
    "factually accurate. You never invent experience, employers, dates, "
    "technologies, metrics, or education. You always answer with a single JSON "
    "object and no surrounding prose or code fences."
)


class OllamaProvider(AIProvider):
    """Talks to a locally running Ollama daemon over its HTTP API."""

    name = "ollama"
    display_name = "Ollama (local)"

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
        temperature: float | None = None,
    ):
        # Read from Django settings, which in turn read the environment. Tests
        # can pass overrides directly, and nothing here is a module constant.
        self.base_url = (base_url or getattr(settings, "OLLAMA_BASE_URL", "")).rstrip("/")
        self.model = model or getattr(settings, "OLLAMA_MODEL", "")
        self.timeout = timeout or getattr(settings, "OLLAMA_TIMEOUT", 180)
        self.temperature = (
            temperature if temperature is not None
            else getattr(settings, "OLLAMA_TEMPERATURE", 0.2)
        )

        if not self.base_url:
            raise AIProviderUnavailableError(
                "AI provider is not configured. Set OLLAMA_BASE_URL.",
                detail="OLLAMA_BASE_URL is empty",
            )

    # ------------------------------------------------------------------
    # AIProvider contract
    # ------------------------------------------------------------------

    def tailor_resume(self, request: TailoringRequest) -> str:
        """Send the tailoring prompt to Ollama and return the raw JSON text."""
        prompt = build_tailoring_prompt(request)

        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            # Ask the daemon for a single, non-streamed JSON response.
            "stream": False,
            "format": "json",
            "options": {
                # Low temperature: this task must stay close to the source
                # text, not improvise.
                "temperature": self.temperature,
            },
        }

        url = f"{self.base_url}/api/chat"
        logger.info(
            "ai.provider_request provider=ollama model=%s",
            self.model or "<unset>",
        )

        try:
            response = requests.post(url, json=body, timeout=self.timeout)
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

        if response.status_code == 404:
            # Ollama returns 404 when the model has not been pulled.
            raise AIProviderUnavailableError(
                "The configured AI model is not installed. "
                f"Run: ollama pull {self.model or '<model>'}",
                detail=f"POST {url} returned 404 for model {self.model!r}",
            )

        if response.status_code >= 400:
            raise AIProviderUnavailableError(
                "The AI provider returned an error. Please try again later.",
                detail=f"POST {url} returned {response.status_code}: "
                f"{response.text[:400]}",
            )

        return self._extract_content(response)

    def health(self) -> tuple[bool, str]:
        """Query ``/api/tags`` to confirm Ollama is up and the model exists."""
        if not self.model:
            return False, "OLLAMA_MODEL is not configured."

        try:
            response = requests.get(
                f"{self.base_url}/api/tags",
                timeout=min(self.timeout, 10),
            )
        except requests.RequestException as exc:
            return False, f"Ollama is not reachable at {self.base_url} ({exc})."

        if response.status_code >= 400:
            return False, f"Ollama returned HTTP {response.status_code}."

        try:
            payload = response.json()
            installed = {
                str(item.get("name", "")).split(":")[0]
                for item in payload.get("models", [])
            }
        except (ValueError, AttributeError):
            return False, "Ollama returned an unreadable response."

        wanted = self.model.split(":")[0]
        if wanted in installed:
            return True, f"Ollama is running and '{wanted}' is installed."

        return False, (
            f"Ollama is running but '{wanted}' is not installed. "
            f"Run: ollama pull {wanted}"
        )

    def describe(self) -> dict[str, Any]:
        # Deliberately omits the URL: it is internal infrastructure, and the
        # brief requires provider configuration to stay server-side.
        return {
            "provider": self.name,
            "display_name": self.display_name,
            "model": self.model or None,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _extract_content(self, response: "requests.Response") -> str:
        """Pull the assistant message out of Ollama's chat envelope."""
        try:
            payload = response.json()
        except ValueError as exc:
            raise AIProviderResponseError(
                "The AI provider returned an unreadable response.",
                detail=f"Non-JSON body: {response.text[:400]}",
            ) from exc

        if not isinstance(payload, dict):
            raise AIProviderResponseError(
                "The AI provider returned an unexpected response.",
                detail=f"Expected an object, got {type(payload).__name__}",
            )

        # Ollama returns {"message": {"content": "..."}, "done": true}
        message = payload.get("message") or {}
        content = message.get("content")

        if content is None:
            # Some builds expose the same text as a top-level "response".
            content = payload.get("response")

        if not isinstance(content, str) or not content.strip():
            raise AIProviderResponseError(
                "The AI provider returned an empty response.",
                detail=f"Keys returned: {sorted(payload.keys())}",
            )

