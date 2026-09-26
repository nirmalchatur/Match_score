"""
Django settings for the automated test environment.

Loaded by ``scripts/api_test_harness.py`` (``DJANGO_SETTINGS_MODULE=config.settings_test``)
so Postman/Newman can exercise a real running server over HTTP.

Everything here exists to make the run hermetic and fast:

* a throwaway SQLite file instead of the developer's ``db.sqlite3``
* ``FastMD5PasswordHasher`` — the tests create several accounts per run and
  PBKDF2 is pure overhead when nothing is being brute-forced
* ``DEBUG = False`` deliberately, because the ``if not DEBUG`` block in
  ``settings.py`` is where the production security posture lives. Running the
  collection with DEBUG off means CI actually exercises SSL-redirect-free local
  HTTP *and* catches settings that only blow up in production.

  The two exceptions are forced back off because Newman talks plain HTTP to
  127.0.0.1: a real redirect to https, or Secure-only cookies, would make every
  authenticated request fail for reasons that have nothing to do with the API.
* media/ uploads are redirected to a temp dir so a resume upload in the test
  collection never touches the working tree.
"""

import tempfile
from pathlib import Path

from .settings import *  # noqa: F401,F403
from .settings import BASE_DIR


# ---------------------------------------------------------------------------
# Database — disposable, isolated from the developer's data
# ---------------------------------------------------------------------------

TEST_DB_PATH = Path(tempfile.gettempdir()) / "tailorup_apitest.sqlite3"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": TEST_DB_PATH,
        "TEST": {"NAME": TEST_DB_PATH},
    }
}

# The real file must never be opened. If TEST_DB_PATH is ever unset or points
# inside the repo, fall back to a temp file rather than the developer's DB.
if BASE_DIR in TEST_DB_PATH.parents:
    TEST_DB_PATH = Path(tempfile.gettempdir()) / "tailorup_apitest_fallback.sqlite3"
    DATABASES["default"]["NAME"] = TEST_DB_PATH
    DATABASES["default"]["TEST"]["NAME"] = TEST_DB_PATH


# ---------------------------------------------------------------------------
# Speed
# ---------------------------------------------------------------------------

# Django 6 removed the Unsalted* hashers entirely, so MD5PasswordHasher (salted
# but still far cheaper than PBKDF2) is the fast option. This matters because the
# collection registers several accounts per run. PBKDF2 stays second so anything
# still referencing it keeps working.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

# Password hashing is the slowest thing in the auth flow; these keep the
# collection's runtime in the seconds range instead of minutes.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]


# ---------------------------------------------------------------------------
# Serve over plain HTTP on 127.0.0.1
#
# settings.py turns on SECURE_SSL_REDIRECT, HSTS and Secure cookies as soon as
# DEBUG is False. Newman uses http://, so a Secure session cookie would never be
# sent back and every authenticated request would 302 to https and die.
# ---------------------------------------------------------------------------

DEBUG = False

SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

ALLOWED_HOSTS = ["*"]

# Newman sends no Origin header, so these only matter if a request is made from
# the Postman app itself. The loopback origins keep local manual runs working.
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS

# django-cors-headers only emits CORS headers for requests carrying an Origin.
CORS_ALLOW_ALL_ORIGINS = False


# ---------------------------------------------------------------------------
# Uploads go to a temp directory, never the working tree
# ---------------------------------------------------------------------------

MEDIA_ROOT = Path(tempfile.gettempdir()) / "tailorup_apitest_media"
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Keep the runner quiet and fast
# ---------------------------------------------------------------------------

# Whitenoise's manifest storage makes `runserver` walk staticfiles on boot.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}

# Django 6 configures mail through MAILERS, not the legacy EMAIL_BACKEND
# setting (see settings.py). Setting EMAIL_BACKEND alongside MAILERS raises
# ImproperlyConfigured, so override the backend inside MAILERS instead. Tests
# should not be able to send real mail, so nothing is delivered.
MAILERS = {
    "default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"},
}
