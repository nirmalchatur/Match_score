"""
API rate limiting.

The point of these tests is not that a throttle class is attached to a view --
that is a one-line assertion and proves nothing. What matters is the behaviour
a client can observe: that the request under the limit succeeds, that the one
over it gets a 429 with a usable Retry-After, and that one account's spending
never eats another's quota.

No test sleeps. DRF's ``SimpleRateThrottle`` keeps counters in the cache and
compares them against a timestamp, so a test clears the cache and fires the
whole quota in microseconds. A test that waited out a real minute would make
this file unusable in a suite.
"""

import contextlib
import os
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

User = get_user_model()

@contextlib.contextmanager
def throttle_rates(**rates):
    """Temporarily set the throttle rate table.

    Why not ``override_settings(REST_FRAMEWORK=...)``: DRF resolves
    ``THROTTLE_RATES`` into a *class attribute* when the throttle classes are
    defined at import time, so reloading the API settings does not change what
    a throttle reads. The first version of this file used override_settings and
    the limits were silently ignored -- every test passed or failed for reasons
    unrelated to the rate. Patching the attribute is what actually moves the
    behaviour, and it restores cleanly afterwards.
    """
    original = dict(SimpleRateThrottle.THROTTLE_RATES)
    SimpleRateThrottle.THROTTLE_RATES = {**original, **rates}
    try:
        yield
    finally:
        SimpleRateThrottle.THROTTLE_RATES = original


def no_limits():
    return throttle_rates(anon=None, user=None, auth=None, signup=None,
                          ai=None, ai_hourly=None, document=None)


class RateLimitTestCase(TestCase):
    """Clears the throttle cache around every test.

    LocMemCache is process-wide, so without this a test that exhausts a limit
    would leave the counter set for the next test, and the suite would start
    depending on execution order.
    """

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.client = APIClient()

    def _user(self, name):
        return User.objects.create_user(username=name, password="pw-for-tests-1234")

    def _drain(self, path, count, client=None):
        """Fire ``count`` requests, returning the status of each."""
        http = client or self.client
        return [http.get(path).status_code for _ in range(count)]


class AnonThrottleTests(RateLimitTestCase):
    """The unauthenticated budget -- the one that faces the internet."""

    def test_under_the_limit_succeeds_and_over_it_is_refused(self):
        with throttle_rates(anon="3/min"):
            codes = self._drain("/api/auth/csrf/", 4)
        self.assertEqual(codes[:3], [200, 200, 200])
        self.assertEqual(codes[3], 429)

    def test_429_body_is_consistent_and_leaks_nothing(self):
        with throttle_rates(anon="30/min"):
            self._drain("/api/auth/csrf/", 30)
            response = self.client.get("/api/auth/csrf/")

        self.assertEqual(response.status_code, 429)
        body = response.json()
        self.assertEqual(body["code"], "rate_limited")
        self.assertEqual(body["detail"], "Too many requests. Please try again later.")

        # A client must not be able to infer the limit, the cache key, the
        # scope, or its own IP. Any of these would let a caller tune itself to
        # sit just under the ceiling.
        serialised = response.content.decode()
        for leak in ("throttle", "cache", "scope", "127.0.0.1", "locmem", "Traceback"):
            self.assertNotIn(leak, serialised)

    def test_retry_after_is_present_and_never_zero(self):
        with throttle_rates(anon="2/min"):
            self._drain("/api/auth/csrf/", 2)
            response = self.client.get("/api/auth/csrf/")

        self.assertEqual(response.status_code, 429)
        retry_after = response.headers.get("Retry-After")
        self.assertIsNotNone(retry_after, "a client needs to know when to retry")
        # Zero invites an immediate retry, which is the opposite of the point.
        self.assertGreaterEqual(int(retry_after), 1)


class UserIsolationTests(RateLimitTestCase):
    """One account's spending must never consume another's quota."""

    def test_user_a_exhausting_the_limit_does_not_block_user_b(self):
        a, b = self._user("rl-a"), self._user("rl-b")
        client_a, client_b = APIClient(), APIClient()
        client_a.force_login(a)
        client_b.force_login(b)

        with throttle_rates(user="5/min"):
            self.assertEqual(self._drain("/api/jobs/", 5, client_a)[-1], 200)
            self.assertEqual(client_a.get("/api/jobs/").status_code, 429)
            # The whole point: B is untouched by A's exhaustion.
            self.assertEqual(client_b.get("/api/jobs/").status_code, 200)

    def test_anonymous_traffic_does_not_consume_a_users_quota(self):
        """The two throttle kinds must be keyed independently."""
        user = self._user("rl-solo")
        client = APIClient()
        client.force_login(user)

        with throttle_rates(anon="2/min", user="5/min"):
            self._drain("/api/auth/csrf/", 5)  # anonymous bucket, now spent
            self.assertEqual(client.get("/api/jobs/").status_code, 200)


class ScopedThrottleTests(RateLimitTestCase):
    """Endpoints that must be stricter or looser than the general budget."""

    def test_login_uses_its_own_strict_limit_not_the_global_one(self):
        """With the general anon budget at 1000/min, login must still stop at 5.

        This is the assertion that the scoped class is actually attached to the
        view. If it were not, login would inherit 1000/min and never throttle.
        """
        with throttle_rates(anon="1000/min", user="1000/min", auth="5/min"):
            for _ in range(5):
                self.client.post(
                    "/api/auth/login/",
                    {"username": "nobody", "password": "wrong"},
                    content_type="application/json",
                )
            response = self.client.post(
                "/api/auth/login/",
                {"username": "nobody", "password": "wrong"},
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["code"], "rate_limited")

    def test_ai_endpoint_refuses_before_the_general_budget_would(self):
        """5/min on tailoring while ordinary reads are allowed 1000/min."""
        user = self._user("rl-ai")
        client = APIClient()
        client.force_login(user)

        with throttle_rates(anon="1000/min", user="1000/min", ai="5/min", ai_hourly=None):
            for _ in range(5):
                response = client.post(
                    "/api/resumes/tailor/", {"job_id": 1}, content_type="application/json"
                )
                self.assertNotEqual(response.status_code, 429)
            response = client.post(
                "/api/resumes/tailor/", {"job_id": 1}, content_type="application/json"
            )
        self.assertEqual(response.status_code, 429)
        self.assertGreaterEqual(int(response.headers["Retry-After"]), 1)

    def test_download_endpoint_has_its_own_limit(self):
        user = self._user("rl-doc")
        client = APIClient()
        client.force_login(user)

        with throttle_rates(anon="1000/min", user="1000/min", document="10/min"):
            codes = self._drain("/api/resumes/1/download/docx/", 12, client)
        self.assertIn(429, codes, "document rendering must be capped separately")
        # It stops at 10, not at 1000 -- which is only true if the scoped class
        # is attached, since the fallback would be the 1000/min user budget.
        self.assertEqual(codes.index(429), 10)


class EnvironmentConfigurationTests(TestCase):
    """Limits must be configurable, and the shipped defaults must be documented.

    These use ``mock.patch.dict`` rather than setting and popping
    ``os.environ`` by hand. The hand-rolled version restored state only on the
    happy path, so a failure in one test left the flag flipped for the next one
    and the class failed in an order-dependent way -- a test that only breaks
    when the file is run as a whole is worse than no test.
    """

    def test_documented_defaults_are_in_force(self):
        from config import settings as s

        with mock.patch.dict(os.environ, {"TAILORUP_RATE_LIMIT_ENABLED": "True"}):
            self.assertEqual(s._rate("AUTH", "5/min"), "5/min")
            self.assertEqual(s._rate("SIGNUP", "5/hour"), "5/hour")
            self.assertEqual(s._rate("ANONYMOUS", "30/min"), "30/min")
            self.assertEqual(s._rate("USER", "60/min"), "60/min")
            self.assertEqual(s._rate("AI", "5/min"), "5/min")
            self.assertEqual(s._rate("AI_HOURLY", "20/hour"), "20/hour")
            self.assertEqual(s._rate("DOCUMENT", "10/min"), "10/min")

    def test_disabling_yields_none_so_throttles_are_inert(self):
        """None, not a malformed string: DRF reads None as "unlimited".

        Reloading the whole settings module is avoided on purpose -- it rebuilds
        every setting object in the process and can leave the suite in a
        different state than it found it. The helper is called directly
        instead, with the environment as the only variable.
        """
        from config import settings as s

        with mock.patch.dict(os.environ, {"TAILORUP_RATE_LIMIT_ENABLED": "False"}):
            self.assertIsNone(s._rate("AUTH", "5/min"))
            self.assertIsNone(s._rate("AI", "5/min"))
        # And the switch is a switch, not a one-way door.
        with mock.patch.dict(os.environ, {"TAILORUP_RATE_LIMIT_ENABLED": "True"}):
            self.assertEqual(s._rate("AUTH", "5/min"), "5/min")

    def test_environment_value_overrides_the_default(self):
        from config import settings as s

        with mock.patch.dict(
            os.environ,
            {"TAILORUP_RATE_LIMIT_ENABLED": "True", "TAILORUP_RATE_LIMIT_AI": "2/min"},
        ):
            self.assertEqual(s._rate("AI", "5/min"), "2/min")
            # An unset scope still falls back to its documented default.
            self.assertEqual(s._rate("AUTH", "5/min"), "5/min")

    def test_every_declared_scope_has_an_entry_in_the_rate_table(self):
        """A missing scope is a 500, not a fallback to unlimited.

        DRF's get_rate() raises KeyError for any scope absent from
        DEFAULT_THROTTLE_RATES. When this was first written only anon and user
        were listed, and every tailored-resume and document call returned 500.
        This test exists to stop that coming back.
        """
        from rest_framework.throttling import SimpleRateThrottle

        from apps.common import throttling

        declared = {
            cls.scope
            for cls in (
                throttling.AnonRateThrottle,
                throttling.UserRateThrottle,
                throttling.StrictAnonRateThrottle,
                throttling.SignupRateThrottle,
                throttling.AIUserRateThrottle,
                throttling.AIHourlyRateThrottle,
                throttling.DocumentRateThrottle,
            )
            if cls.scope
        }
        self.assertTrue(declared)
        for scope in declared:
            self.assertIn(scope, SimpleRateThrottle.THROTTLE_RATES, scope)
