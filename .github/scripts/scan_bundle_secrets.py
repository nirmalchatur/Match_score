#!/usr/bin/env python3
"""
Fail the build if anything in the built frontend bundle looks like a credential.

Why scan the built output rather than grep the source
----------------------------------------------------
Vite inlines every ``VITE_``-prefixed environment variable into the bundle at
build time, in plaintext, where anyone can read it in devtools. So the file
that matters is ``dist/``, not the ``.tsx`` it was compiled from. A source grep
cannot see a leak that happens during bundling, which is precisely the leak
this project is most likely to cause by accident.

The caller is expected to have built with a canary value in the environment
(see ``.github/workflows/security.yml``); this script then asserts that the
canary did *not* survive into the output. That is a positive test of the
property we care about, not a heuristic for "does this string look secret".

Exit codes: 0 clean, 1 a finding was reported.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

#: Files worth reading. Everything else in dist/ is a copy or a map.
TEXT_SUFFIXES = {".js", ".mjs", ".cjs", ".css", ".html", ".json", ".map"}

#: Baked into the build env on purpose. Finding it here is a hard failure:
#: it proves the environment reached the browser, which is the whole risk.
CANARIES = [
    re.compile(r"AIzaSy[A-Za-z0-9_\-]{10,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{16,}"),
    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"xox[abposr]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]

#: Assignment shapes, used to report a human-readable location.
ASSIGNMENT = re.compile(
    r"""(?ix)
    \b(
        api[_-]?key | secret | password | passwd | token |
        access[_-]?key | client[_-]?secret | private[_-]?key | credential
    )\b
    \s* [:=] \s*
    ['"] (?P<value> [A-Za-z0-9_\-\/\+=]{16,} ) ['"]
    """
)

#: The name of a build-inlined secret, as a single token. No wildcards in
#: between, because a source map is one long JSON line: a pattern with `.*`
#: in it will happily span from an unrelated `VITE_API_URL` to a `TOKEN`
#: thousands of characters later and report a leak that does not exist.
#:
#: This exact false positive happened, and it matters: a scanner that cries
#: wolf gets switched off, which is worse than having no scanner.
SENSITIVE_NAME = re.compile(
    r"\b(?:VITE|REACT_APP|NEXT_PUBLIC)_[A-Z0-9_]*"
    r"(?:API_KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL|PRIVATE_KEY)\b"
)

#: The higher-signal shape: the bundle actually *reading* such a variable.
#: Anchored to a real member access, so a prose mention in a comment cannot
#: match it.
SECRET_ACCESS = re.compile(
    r"(?:import\.meta\.env|process\.env|window\.__ENV__)\s*[.?]?\s*"
    r"['\"]?(?:VITE|REACT_APP|NEXT_PUBLIC)_[A-Z0-9_]*"
    r"(?:API_KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL|PRIVATE_KEY)"
)

#: Values that are obviously not secrets, so the assignment rule stays quiet.
PLACEHOLDER = re.compile(
    r"(?i)^(?:x{4,}|\*{4,}|changeme|placeholder|your[_-].*|example|test|dummy|"
    r"none|null|undefined|true|false|\$\{.*\}|process\.env\..*|<.*>)$"
)


def iter_text_files(root: Path):
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
            yield path


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: scan_bundle_secrets.py <dist-dir>", file=sys.stderr)
        return 2

    root = Path(argv[1])
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    files = list(iter_text_files(root))
    findings: list[str] = []

    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        for pattern in CANARIES:
            for match in pattern.finditer(text):
                findings.append(
                    f"{path}: credential-shaped value "
                    f"({pattern.pattern[:28]}...) at offset {match.start()}"
                )

        for match in ASSIGNMENT.finditer(text):
            value = match.group("value")
            if PLACEHOLDER.match(value):
                continue
            findings.append(
                f"{path}: literal assigned to {match.group(1)!r} at offset {match.start()}"
            )

        for match in SECRET_ACCESS.finditer(text):
            findings.append(
                f"{path}: bundle reads a browser-exposed secret variable "
                f"({match.group(0)[:60]}) at offset {match.start()}"
            )

        for match in SENSITIVE_NAME.finditer(text):
            findings.append(
                f"{path}: mentions a build-inlined secret variable "
                f"({match.group(0)}) at offset {match.start()}"
            )

    scanned = len(files)
    if findings:
        print(f"FAIL: {len(findings)} potential secret(s) in {root} ({scanned} files scanned)\n")
        for line in findings[:60]:
            print("  " + line)
        if len(findings) > 60:
            print(f"  ... and {len(findings) - 60} more")
        return 1

    print(f"OK: no credential material found in {root} ({scanned} files scanned)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
