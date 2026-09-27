"""
Cookie attributes for a cross-origin deployment.

The SPA is served from Vercel and the API from Render, so the browser treats
every call as *cross-site*. That makes the cookie flags load-bearing rather
than cosmetic, and the failure they cause is baffling: signup succeeds, the
response sets a session cookie, and then every later request arrives
anonymous with "Authentication credentials were not provided" -- which reads
like a backend bug and is really a browser refusing the cookie.

The production posture cannot be read off the live settings object, because
``settings_test`` deliberately forces ``DEBUG`` off and then turns the secure
flags back off for plain-HTTP Newman runs. So this module evaluates
``config.settings`` in a **subprocess** with ``DEBUG=false`` and inspects the
result. Reloading the module in-process would swap the settings object out
from under the running test session and corrupt every other test.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

BACKEND_DIR = Path(__file__).resolve().parents[3]

# Evaluated with DEBUG off, printing exactly the four values that decide
# whether a cross-site browser will send the cookies back.
PROBE = """
import json, os, sys
os.environ["DEBUG"] = "false"
sys.path.insert(0, %(backend)r)
import config.settings as s

def flag(name):
    # getattr with a sentinel rather than a direct access: a module that
    # never sets the cookie flags would raise AttributeError, and the test
    # would report "could not evaluate settings" instead of the actionable
    # "SESSION_COOKIE_SAMESITE is UNSET".
    return getattr(s, name, "UNSET")

print("<<<" + json.dumps({
    "session_samesite": flag("SESSION_COOKIE_SAMESITE"),
    "csrf_samesite": flag("CSRF_COOKIE_SAMESITE"),
    "session_secure": flag("SESSION_COOKIE_SECURE"),
    "csrf_secure": flag("CSRF_COOKIE_SECURE"),
}) + ">>>")
""" % {"backend": str(BACKEND_DIR)}


class CrossOriginCookieTests(SimpleTestCase):
    """The production cookie posture the deployed SPA depends on."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        result = subprocess.run(
            [sys.executable, "-c", PROBE],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0 or "<<<" not in result.stdout:
            raise AssertionError(
                "could not evaluate config.settings with DEBUG off\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        payload = result.stdout.split("<<<", 1)[1].split(">>>", 1)[0]
        cls.settings = json.loads(payload)

    def test_session_cookie_is_samesite_none_in_production(self):
        self.assertEqual(
            self.settings["session_samesite"],
            "None",
            "A SameSite=Lax session cookie is not sent on the cross-site "
            "requests the Vercel SPA makes, so the user is logged out on "
            "every call after signup.",
        )

    def test_csrf_cookie_is_samesite_none_in_production(self):
        self.assertEqual(
            self.settings["csrf_samesite"],
            "None",
            "The CSRF cookie is read by JavaScript on another origin, so it "
            "needs the same treatment as the session cookie.",
        )

    def test_samesite_none_is_always_paired_with_secure(self):
        """Browsers reject SameSite=None without Secure.

        Separating the two silently produces a cookie that is set but never
        sent -- the same symptom as the bug this module exists to prevent.
        """
        self.assertTrue(
            self.settings["session_secure"],
            "SESSION_COOKIE_SECURE must be True: browsers discard a "
            "SameSite=None cookie that is not also Secure.",
        )
        self.assertTrue(
            self.settings["csrf_secure"],
            "CSRF_COOKIE_SECURE must be True for the same reason.",
        )

    def test_both_cookies_agree(self):
        """A mismatch means one flow breaks while the other works."""
        self.assertEqual(
            self.settings["session_samesite"],
            self.settings["csrf_samesite"],
            "Session and CSRF cookies should use the same SameSite policy.",
        )

