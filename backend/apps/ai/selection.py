"""
Credential resolution: which API key does a tailoring call actually use?

Why this module exists
---------------------
Before it, key resolution was spread across three places that each guessed: the
Gemini provider read ``request.api_key`` and nothing else, the tailoring view
looked up a hardcoded ``provider="gemini"`` row, and the status endpoint decided
the button's enabled state from yet another rule. Adding a second hosted
provider meant all three would have to change in step.

They now all call here instead, and the rule is stated once:

    1. **The user's own key wins.** If they saved one, it is used. A deployment
       key must never silently override a key someone deliberately provided.
    2. **Otherwise the deployment's env key, if any.** This is the fallback the
       hosted deployments rely on: set ``GEMINI_API_KEY`` / ``GROQ_API_KEY`` and
       a visitor can tailor a resume without pasting anything.
    3. **Otherwise nothing**, and the provider raises a clear, actionable error.

The ordering matters and is asserted in the tests. It is also the only reason
this is safe to offer: a deployment that leaves both env variables empty behaves
exactly as it did before, and every test that asserted "bring-your-own-key
only" still passes without being edited.
"""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


#: Providers that can be configured with a deployment-owned env key. Ollama is
#: absent because it is keyless, and ``fake`` because it never talks to a
#: network. Kept as a set of *provider slugs*, deliberately not free text.
HOSTED_PROVIDERS = ("gemini", "groq")


def deployment_api_key(provider: str) -> str:
    """
    The env-configured key for ``provider``, or "" when none is set.

    Read through ``getattr`` with a default so this works under a settings
    module that predates the variable -- an ``override_settings`` test, or a
    third-party settings import -- instead of raising ``AttributeError`` in the
    middle of a request.
    """
    slug = (provider or "").strip().lower()
    if slug not in HOSTED_PROVIDERS:
        return ""
    return (getattr(settings, f"{slug.upper()}_API_KEY", "") or "").strip()


def has_deployment_key(provider: str) -> bool:
    """True when the deployment itself can pay for this provider."""
    return bool(deployment_api_key(provider))


def _stored_user_key(user, provider: str) -> str:
    """
    The caller's own decrypted key for ``provider``, or "".

    Returns a plain string rather than the model so a caller cannot keep a
    database object -- and therefore the ciphertext -- alive past the request.

    Raises :class:`~apps.users.crypto.CredentialCryptoError` only when a row
    exists but cannot be decrypted; ``reveal_key`` removes that row on the way
    out, so the next request honestly reports "not configured".
    """
    try:
        from apps.users.models import ProviderCredential
    except Exception:  # pragma: no cover - defensive
        return ""

    credential = ProviderCredential.objects.filter(
        user=user,
        provider=provider,
    ).first()

    if credential is None:
        return ""

    return credential.reveal_key()


def resolve_api_key(user, provider: str) -> str:
    """
    Return the key to use for one call, and nothing else.

    The function is deliberately total: every combination of (user key set?,
    deployment key set?) returns something, and the empty string always means
    "the caller must surface a 'add your key' message". Callers never branch on
    which of the two sources they got, because that distinction is a logging
    concern and nothing more -- the key is opaque either way.
    """
    slug = (provider or "").strip().lower()

    try:
        user_key = _stored_user_key(user, slug)
    except Exception:
        # A crypto failure must not become a 500 here. The row has already been
        # dropped by reveal_key(), so the correct behaviour is to fall through
        # to the deployment key -- and, if there is none, to the normal
        # "no key" path, which the provider turns into a 503 with a message the
        # user can act on.
        logger.warning(
            "ai.credential_unreadable provider=%s; falling back", slug, exc_info=True
        )
        user_key = ""

    if user_key:
        return user_key

    fallback = deployment_api_key(slug)
    if fallback:
        # Not logged at info: the value is a secret, and even a truncated hint
        # in a log is one more copy to rotate. The provider slug is enough.
        logger.info(
            "ai.using_deployment_key provider=%s", slug
        )
        return fallback

    return ""


def provider_needs_user_key(provider: str) -> bool:
    """
    True when tailoring cannot run for this provider without a key from *some*
    source.

    The name is the reason this is a function and not a literal: the status
    endpoint used to report ``requires_user_key`` for a provider that was in
    fact fully usable because the deployment held a key. That disabled the
    tailor button for every user on a working deployment. It now means
    "needs a key that only this user can supply", which is the only case the
    button should actually be disabled for.
    """
    return (provider or "").strip().lower() in HOSTED_PROVIDERS and not has_deployment_key(
        provider
    )


# ---------------------------------------------------------------------------
# Provider *selection* -- which backend runs, as opposed to which key pays.
#
# Kept below the credential rules above because it depends on them: a choice of
# "gemini" is only usable if a key can be obtained for it, and that now includes
# the deployment's own env key.
# ---------------------------------------------------------------------------


#: Provider slugs a user is allowed to select. Deliberately not free text: an
#: unknown slug would reach the registry lookup and surface as a 500, and a
#: free-text field is an unnecessary place to validate input.
SELECTABLE = ("gemini", "groq", "ollama")


def default_provider_name() -> str:
    """The deployment-wide provider, normalised, or "" when unconfigured."""
    return (getattr(settings, "AI_PROVIDER", "") or "").strip().lower()


def can_authenticate(user, provider: str) -> bool:
    """
    True when a tailoring call for ``provider`` would have a key to send.

    Satisfied by *either* source: a credential this user saved, or a deployment
    env key. This is the check that decides whether an explicit choice is
    honoured, and the reason it consults :func:`_stored_user_key` rather than a
    bare ``.exists()`` -- a row whose ciphertext cannot be decrypted exists but
    cannot authenticate anything.
    """
    slug = (provider or "").strip().lower()

    if slug not in HOSTED_PROVIDERS:
        # Keyless (ollama) or non-network (fake): nothing to authenticate.
        return True

    try:
        if _stored_user_key(user, slug):
            return True
    except Exception:
        # Undecryptable, and reveal_key() has just dropped the row.
        logger.warning("ai.credential_unreadable provider=%s", slug, exc_info=True)

    return has_deployment_key(slug)


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

    # A hosted choice with no key from *any* source is a *missing key*,
    # whatever the deployment default happens to be. That check is made first
    # and unconditionally because the two reasons lead to different UI: "add
    # your key" is actionable, "your choice is unavailable here" is not.
    #
    # Note this now consults can_authenticate(), which is satisfied by the
    # deployment env key too. On a Render deploy that sets GEMINI_API_KEY, a user
    # who picked Gemini and saved nothing is correctly reported as ready rather
    # than as blocked forever.
    if choice in HOSTED_PROVIDERS and not can_authenticate(user, choice):
        return configured, "missing_key"

    # A choice the deployment does not itself support is not an error, just
    # inapplicable: someone who picked "local Ollama" on a Gemini-only
    # deployment gets the deployment default rather than a failed request.
    if configured and choice != configured:
        # A hosted choice is honoured even when the deployment default is
        # something else, because it is usable without any server configuration
        # beyond a key -- per-user, or a deployment fallback. Ollama is not: it
        # needs OLLAMA_BASE_URL to point somewhere real, which is a server-side
        # fact we cannot invent.
        if choice in HOSTED_PROVIDERS:
            return choice, "user_choice"
        return configured, "choice_unavailable"

    return configured, "user_choice"

