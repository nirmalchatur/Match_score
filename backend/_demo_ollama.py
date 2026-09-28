"""
A real, small generation against the local Ollama daemon.

Not part of the test suite, and not a tailoring run. It exists because "is it
wired up" and "does the model actually produce text" are different questions,
and answering the second one through the tailoring pipeline costs minutes on
CPU.

It talks to Ollama's HTTP API directly rather than through
``provider.tailor_resume`` for two reasons, both worth being explicit about:

  * A real request builds the full tailoring prompt from a resume, a job and a
    match analysis, and asks for JSON covering every section. On CPU that is
    the ~364s run. Capping generated tokens instead proves the transport, the
    model and the output while returning in seconds.
  * A short direct call cannot be mistaken for evidence that the tailoring
    *contract* holds. That is covered by the test suite using FakeProvider,
    and by the one real end-to-end run already recorded in the docs.

Run from `backend/`:  python _demo_ollama.py
"""

import os
import sys
import time

import django
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # noqa: E402


def main() -> int:
    base = (settings.OLLAMA_BASE_URL or "").rstrip("/")
    model = settings.OLLAMA_MODEL

    if not base or not model:
        print("OLLAMA_BASE_URL / OLLAMA_MODEL are not set.")
        print("Run _check_provider.py first.")
        return 1

    print("endpoint :", base)
    print("model    :", model)
    print()

    print("sending one real request (capped, so it returns quickly)...")
    started = time.monotonic()
    try:
        response = requests.post(
            f"{base}/api/generate",
            json={
                "model": model,
                "prompt": "In one short sentence, what does a resume tailoring tool do?",
                # The cap is the whole reason this returns in seconds rather
                # than minutes. Remove it to see the real cost of a full run.
                "options": {"num_predict": 48, "temperature": 0.2},
                "stream": False,
            },
            timeout=settings.OLLAMA_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print("  request failed after %.1fs: %s" % (time.monotonic() - started, exc))
        return 1

    elapsed = time.monotonic() - started
    payload = response.json()
    text = (payload.get("response") or "").strip()

    print("  took        : %.1f seconds" % elapsed)
    print("  eval_count  :", payload.get("eval_count", "?"))
    print("  total_ms    :", int(payload.get("total_duration", 0) / 1_000_000))
    print()
    print("--- real model output ---")
    print(text)
    print("--- end ---")
    print()
    print("That is a real llama3.1 response from your own machine.")
    print("A full tailoring run uses a far longer prompt and asks for JSON")
    print("covering every resume section, so it takes several minutes on CPU.")
    return 0 if text else 1


if __name__ == "__main__":
    raise SystemExit(main())
