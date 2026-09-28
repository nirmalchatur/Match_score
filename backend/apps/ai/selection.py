"""
Per-user provider selection.

Why this exists
---------------
``UserProfile.ai_setup`` already recorded whether a candidate picked a local
model or a hosted one during onboarding, but it was inert: it only steered
which instructions the Settings screen showed. The provider actually used came
from the server-wide ``AI_PROVIDER``, so a deployment could not offer both.

The rule this module encodes is deliberately conservative, because the failure
mode of guessing wrong here is not a crash -- it is **sending someone's resume
to a third party they did not intend to send it to**. TailorUp's central claim is
that a resume need not leave the machine, so the choice is never inferred from
"a credential happens to exist".

Precedence
----------
1. No choice recorded, or a choice that no longer makes sense -> the
   deployment default.
2. Choice is ``gemini`` and this user has a stored Gemini credential -> Gemini.
3. Choice is ``ollama`` and the deployment is configured for Ollama -> Ollama.

Every fallback is *reported*, never silent. The status endpoint returns both
the effective provider and why it was chosen, so the UI can say "you picked
Gemini but no key is saved" instead of failing opaquely.
"""

from __future__ import annotations

from django.conf import settings


#: Provider slugs a user is allowed to select. Deliberately not free text: an
#: unknown slug would reach the registry lookup and surface as a 500, and a
#: free-text field is an unnecessary place to validate input.
SELECTABLE = ("gemini", "ollama")


def default_provider_name() -> str:
    """The deployment-wide provider, normalised, or "" when unconfigured."""
    return (getattr(settings, "AI_PROVIDER", "") or "").strip().lower()


def resolve_provider_name(user) -> tuple[str, str]:
    """
    Return ``(provider_name, reason)`` for one user.

    ``reason`` is a short machine-readable token the frontend can map to a
    sentence. It is part of the response rather than a log line because "why is
    my resume going to Google" is a question the user is entitled to have
    answered, at the moment they ask it.
    """
    configured = default_provider_name()

    profile = getattr(user, "profile", None)
    choice = (getattr(profile, "ai_setup", "") or "").strip().lower()

    if choice not in SELECTABLE:
        return configured, "default"

    # A Gemini choice with no credential is a *missing key*, whatever the
    # deployment default happens to be. That check is made first and
    # unconditionally because the two reasons lead to different UI: "add your
    # key" is actionable, "your choice is unavailable here" is not. Getting
    # this backwards would tell someone who simply forgot to paste a key that
    # their provider is unsupported, which is true of neither.
    if choice == "gemini" and not _has_credential(user, "gemini"):
        return configured, "missing_key"

    # A choice the deployment does not itself support is not an error, just
    # inapplicable: someone who picked "local Ollama" on a Gemini-only
    # deployment gets the deployment default rather than a failed request.
    if configured and choice != configured:
        # Gemini is usable without server configuration because the credential
        # is per-user, so a gemini choice is honoured even when the deployment
        # default is something else. Ollama is not: it needs OLLAMA_BASE_URL to
        # point somewhere real, which is a server-side fact we cannot invent.
        if choice == "gemini":
            return "gemini", "user_choice"
        return configured, "choice_unavailable"

    return configured, "user_choice"


def _has_credential(user, provider: str) -> bool:
    """True when this user has a stored credential for ``provider``.

    Imported lazily and defensively: the credentials app is optional in some
    test configurations, and a missing app must read as "no key" rather than
    take down the status endpoint.
    """
    try:
        from apps.users.models import ProviderCredential
    except Exception:  # pragma: no cover - defensive
        return False

    return ProviderCredential.objects.filter(user=user, provider=provider).exists()
