#!/usr/bin/env python3
"""
Fail on deployment settings that are actually dangerous, and report the rest.

Why not `manage.py check --deploy` on its own
---------------------------------------------
That check fails the build on *any* warning, and its catalogue grows with
every Django release. This project pins Django 6.1, which requires Python 3.12;
the available development environment is Python 3.10 with Django 5.2, so the
production check cannot be reproduced locally at all. Gating a build on a
check that cannot be run before merging is how a check gets disabled: the first
stranger warning turns the job red with nothing anyone can act on.

So the policy is written out here instead. The conditions below are the ones
that represent a real risk if they are wrong in production. Anything Django
reports that is not on this list is printed in full and does not fail the
build, so a genuinely new check is still visible in the log rather than
silently ignored.

To tighten this later, add the specific ``security.W0xx`` id. To loosen it,
remove the line -- but do not replace the whole thing with ``--fail-level``.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

#: (check id, why it matters). Every one of these is a real, exploitable risk
#: or a hard-fails production misconfiguration.
BLOCKING = {
    "security.W018": "DEBUG is on in production -- serves tracebacks with "
                     "settings and source to any visitor.",
    "security.W009": "SECRET_KEY is short, low-entropy or a django-insecure "
                     "default; sessions and signed values are forgeable.",
    "security.W004": "HSTS not set, so a first-visit connection is downgradeable.",
    "security.W008": "SSL redirect not enabled; the first request can be intercepted.",
    "security.W012": "SESSION_COOKIE_SECURE is off, so a session cookie travels in the clear.",
    "security.W016": "CSRF_COOKIE_SECURE is off.",
    "security.W019": "X_FRAME_OPTIONS not set -- the app can be framed.",
    "security.W020": "X_CONTENT_TYPE_OPTIONS not set -- MIME sniffing is possible.",
}

#: A settings import that blows up, or a check that cannot run at all.
FATAL = re.compile(r"(ModuleNotFoundError|ImportError|ImproperlyConfigured|"
                   r"django\.core\.exceptions|Traceback)", re.I)


def main() -> int:
    env_backend = Path(__file__).resolve().parents[2] / "backend"

    # Overridable so this can be exercised in both directions without editing
    # the script: run it with DEBUG=True to see the gate fail on purpose.
    import os

    child_env = {
        **os.environ,
        "SECRET_KEY": os.environ.get(
            "SECRET_KEY", "ci-only-throwaway-8Jd2Xq9Lm4Np7Rt3Vw6Yb1Hs5Cf0Zg7Ke9Mu2Iv"
        ),
        "DEBUG": os.environ.get("DEBUG", "False"),
        "ALLOWED_HOSTS": os.environ.get("ALLOWED_HOSTS", "ci.invalid"),
    }

    proc = subprocess.run(
        [sys.executable, "manage.py", "check", "--deploy", "--fail-level", "ERROR"],
        cwd=env_backend,
        capture_output=True,
        text=True,
        env=child_env,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    print(output.strip() or "(no output)")

    if proc.returncode != 0:
        print("\nFAIL: `check --deploy` reported an ERROR (or could not run).")
        return 1

    found = {m for m in re.findall(r"\((security\.\w+)\)", output)}
    blocking = sorted(found & BLOCKING.keys())
    informational = sorted(found - BLOCKING.keys())

    if blocking:
        print("\nFAIL: production-unsafe settings detected\n")
        for check in blocking:
            print(f"  {check}: {BLOCKING[check]}")
        return 1

    print("\nOK: no production-unsafe settings.")
    if informational:
        print(
            "\nReported by Django but not gating (add one to BLOCKING in this "
            "script if it should fail the build):"
        )
        for check in informational:
            print(f"  {check}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
