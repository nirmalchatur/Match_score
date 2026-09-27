"""
Maps ``AI_PROVIDER`` to a concrete :class:`~apps.ai.providers.base.AIProvider`.

This is the only place that knows the set of available providers. Adding a new
one is a single ``register`` call (or one entry in ``_BUILTIN``) and requires
**no change** to :class:`apps.ai.tailor.ResumeTailor`, which only ever talks to
the :class:`AIProvider` interface.

Configuration
-------------
    AI_PROVIDER=ollama     # local development: a local Ollama daemon
    AI_PROVIDER=gemini     # hosted deployment: Google AI Studio
    AI_PROVIDER=fake        # tests / CI: deterministic, no network

Ollama is the local default because it needs no key. Render and similar hosts
cannot run a daemon, so a hosted deployment sets ``gemini`` and either a
server-wide ``GEMINI_API_KEY`` or lets each user bring their own.
"""

from __future__ import annotations

import logging
from typing import Callable

from .exceptions import AIConfigurationError
from .providers.base import AIProvider
from .providers.fake import FakeAIProvider
from .providers.gemini import GeminiProvider
from .providers.ollama import OllamaProvider

logger = logging.getLogger(__name__)

#: Provider name -> zero-argument factory. Values are callables rather than
#: classes so a provider can be constructed lazily with its own overrides.
_BUILTIN: dict[str, Callable[[], AIProvider]] = {
    "ollama": OllamaProvider,
    "gemini": GeminiProvider,
    "fake": FakeAIProvider,
}

#: Process-wide overrides registered at runtime (used by tests).
_registry: dict[str, Callable[[], AIProvider]] = dict(_BUILTIN)


def register(name: str, factory: Callable[[], AIProvider]) -> None:
    """
    Register (or replace) a provider under ``name``.

    Lets a future hosted provider be plugged in from its own module without
    editing this file::

        from apps.ai import factory
        factory.register("openai", lambda: OpenAIProvider(api_key=settings.X))
    """
    key = (name or "").strip().lower()
    if not key:
        raise AIConfigurationError(
            "A provider name is required.",
            detail="register() called with an empty name",
        )
    _registry[key] = factory


def available_providers() -> list[str]:
    """Names that :func:`get_ai_provider` accepts."""
    return sorted(_registry)


def get_ai_provider() -> AIProvider:
    """
    Build the configured provider.

    Raises :class:`AIConfigurationError` when ``AI_PROVIDER`` is unset or names a
    provider that is not registered. That is deliberately a configuration error
    rather than a silent fallback to a stub: falling back would let a
    misconfigured deployment look healthy while serving canned text to users.
    """
    from django.conf import settings

    name = (getattr(settings, "AI_PROVIDER", "") or "").strip().lower()

    if not name:
        raise AIConfigurationError(
            "AI is not configured. Set AI_PROVIDER to enable resume tailoring.",
            detail="AI_PROVIDER is empty",
        )

    try:
        factory = _registry[name]
    except KeyError:
        raise AIConfigurationError(
            f"AI provider '{name}' is not available.",
            detail=f"AI_PROVIDER={name!r}; registered: {available_providers()}",
        ) from None

    return factory()


def describe_provider() -> dict:
    """
    Non-secret provider metadata, safe to expose through the API.

    Never includes the base URL or any credential: provider configuration must
    stay server-side.
    """
    try:
        provider = get_ai_provider()
    except AIConfigurationError as exc:
        return {
            "provider": None,
            "available": False,
            "message": exc.message,
            "registered": available_providers(),
        }

    described = provider.describe()
    described["available"] = True
    return described
