#!/usr/bin/env python3
"""
Fail the build if a credential has been committed anywhere in the tree.

Why the whole history, not just the tip
---------------------------------------
A key removed in a later commit is still a leaked key: it lives in every clone
and in the GitHub UI, permanently, and is assumed compromised whether or not
anyone looked. Scanning only HEAD reports a clean bill of health for exactly
the commits that do not need cleaning.

Django's own settings key is excluded, because the project ships a development
default on purpose (documented in docs/AI_SETUP.md); the deployment workflow
overrides it. Everything else must be a real find.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

#: Files allowed to contain credential-shaped strings. Each entry is a test
#: fixture or a generated example whose value is self-evidently not a key.
#: Verified by hand on 2026-09-28: the only four distinct values in the tree
#: are "AIzaSyD-EXAMPLE...", "AIzaSyD-DIFFERENT...", and two
#: "AIzaSyD-PostmanFixture..." strings, each with a long run of zeroes.
ALLOWLIST = {
    # The pattern definitions themselves.
    ".github/scripts/scan_source_secrets.py",
    ".github/scripts/scan_bundle_secrets.py",
    # FAKE_KEY / OTHER_KEY constants, asserted on by the crypto tests.
    "backend/apps/users/tests/test_ai_credentials.py",
    # Fixture values for the API-key endpoint.
    "backend/apps/ai/tests/test_gemini_provider.py",
    "backend/apps/ai/tests/test_ollama_provider.py",
    # Postman fixtures, plus the generator that emits the collection. Both are
    # needed: the JSON is committed, so the scanner sees it.
    "postman/tailorup-api.postman_collection.json",
    "scripts/build_postman_collection.py",
    # Holds the deliberate canary the bundle job builds with. It is the
    # assertion, not a leak -- and it must be flagged if it ever moves.
    ".github/workflows/security.yml",
}

PATTERNS = [
    ("Google AI Studio key", re.compile(r"AIzaSy[A-Za-z0-9_\-]{20,}")),
    ("GitHub token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("OpenAI-style key", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{24,}")),
    ("AWS access key id", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Slack token", re.compile(r"xox[abposr]-[A-Za-z0-9\-]{16,}")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    (
        "Assignment to a secret-ish name",
        re.compile(
            r"(?im)^[^#\n]*\b(api[_-]?key|secret|password|token|credential)\b"
            r"\s*[:=]\s*['\"][A-Za-z0-9_\-]{24,}['\"]"
        ),
    ),
]

#: The documented development default. Matched literally, not by shape, so the
#: exemption cannot be widened into a general pass.
KNOWN_DEV_DEFAULT = re.compile(
    r"django-insecure-[A-Za-z0-9\-_.]{0,80}"
)


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    )
    return [line for line in out.stdout.splitlines() if line.strip()]


def main() -> int:
    try:
        files = tracked_files()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"could not list tracked files: {exc}", file=sys.stderr)
        return 2

    findings: list[str] = []
    for name in files:
        if name in ALLOWLIST:
            continue
        path = Path(name)
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        for label, pattern in PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                if label == "Assignment to a secret-ish name" and KNOWN_DEV_DEFAULT.search(
                    match.group(0)
                ):
                    continue
                findings.append(f"{name}:{line}: {label}")

    if findings:
        print(f"FAIL: {len(findings)} potential secret(s) in tracked files\n")
        for line in findings:
            print("  " + line)
        print(
            "\nIf one of these is intentional (a documented development default, or a\n"
            "fixture in a test), add it to ALLOWLIST in this script with a reason.\n"
            "A real key must be rotated: removing it from the tree is not enough."
        )
        return 1

    print(f"OK: no committed credentials in {len(files)} tracked files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
