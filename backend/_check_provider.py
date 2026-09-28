"""
Ad-hoc local check: is Django actually pointed at the local Ollama?

Not part of the test suite and not imported by the app. Run it with
`python _check_provider.py` from `backend/` when setting up a machine and
you want to know whether the provider is wired before starting a server.

Deliberately read-only: it describes the provider and asks Ollama whether it
is answering. It never sends a resume anywhere and never generates anything,
so it is safe to run repeatedly while wiring things up.
"""

import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # noqa: E402

from apps.ai import factory  # noqa: E402


def main() -> int:
    print("AI_PROVIDER      :", repr(settings.AI_PROVIDER))
    print("OLLAMA_BASE_URL  :", settings.OLLAMA_BASE_URL or "(unset)")
    print("OLLAMA_MODEL     :", settings.OLLAMA_MODEL or "(unset)")
    print("OLLAMA_TIMEOUT   :", settings.OLLAMA_TIMEOUT)
    print("registered       :", ", ".join(factory.available_providers()))
    print()

    described = factory.describe_provider()
    for key in ("provider", "model", "available", "message"):
        if key in described:
            print("  %-10s :" % key, described[key])

    # describe() only reads settings. This is the call that actually touches
    # the network, so it is what distinguishes "configured" from "reachable".
    try:
        provider = factory.get_ai_provider()
    except Exception as exc:  # noqa: BLE001 - this is a diagnostic script
        print("\n  could not build provider:", exc)
        return 1

    print("\n  asking the daemon whether it is alive...")
    try:
        ok, detail = provider.health()
    except Exception as exc:  # noqa: BLE001
        print("  daemon unreachable:", exc)
        print("  is `ollama serve` running? is the model pulled?")
        return 1

    print("  health          :", ok)
    if detail:
        print("  detail          :", detail)
    if not ok:
        print("  the provider was built but the daemon did not answer.")
        print("  check OLLAMA_BASE_URL matches where ollama is actually listening.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
