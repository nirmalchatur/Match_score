"""
Authentication tests: signup, login, logout, and current-user.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class RegistrationTests(TestCase):
    def test_register_creates_account_and_returns_user(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "email": "new@example.com",
                "password": "sup3r-secret-pw",
                "full_name": "Ada Lovelace",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["user"]["email"], "new@example.com")
        self.assertTrue(User.objects.filter(email="new@example.com").exists())

    def test_register_hashes_password(self):
        self.client.post(
            "/api/auth/register/",
            {
                "email": "hash@example.com",
                "password": "sup3r-secret-pw",
            },
            content_type="application/json",
        )

        user = User.objects.get(email="hash@example.com")
        self.assertNotEqual(user.password, "sup3r-secret-pw")
        self.assertTrue(user.check_password("sup3r-secret-pw"))


class CsrfTokenTests(TestCase):
    """The SPA must be able to obtain a CSRF token it can actually read.

    The SPA is on a different origin from the API, so `document.cookie`
    cannot see the `csrftoken` cookie. The token therefore has to be
    delivered in the response body as well as the cookie, or every
    mutating request fails with "CSRF token missing".

    Two things make these tests easy to write wrong:

    * The default test client sets ``enforce_csrf_checks=False``, so CSRF is
      silently skipped and a token is never actually exercised. These use an
      explicitly enforcing client.
    * ``register`` and ``login`` declare ``authentication_classes = []``,
      which bypasses ``SessionAuthentication`` and therefore CSRF entirely. A
      token test pointed at ``register`` passes whether or not the token is
      real, so these are written against ``logout``, which uses the default
      classes and does enforce it.
    """

    def setUp(self):
        super().setUp()
        # This project reuses django.contrib.auth.models.User, whose USERNAME_FIELD
        # is still "username" even though the API is email-based, so create_user
        # takes the email positionally as the username.
        self.user = User.objects.create_user(
            "csrf@example.com", "csrf@example.com", "sup3r-secret-pw"
        )

    def _enforcing_client(self):
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        return client

    def test_token_is_returned_in_the_body(self):
        response = self.client.get("/api/auth/csrf/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("csrf_token", response.data)
        self.assertTrue(response.data["csrf_token"])

    def test_token_is_also_set_as_a_cookie(self):
        # DRF's SessionAuthentication compares the header against the cookie,
        # so the cookie is not optional even when the body carries the token.
        response = self.client.get("/api/auth/csrf/")
        self.assertIn("csrftoken", response.cookies)

    def test_endpoint_needs_no_session(self):
        """It is called before signing in, so it must not require auth."""
        response = self.client.get("/api/auth/csrf/")
        self.assertEqual(response.status_code, 200)

    def test_token_is_accepted_on_a_mutating_request(self):
        """End-to-end proof: the token from this endpoint passes CSRF."""
        client = self._enforcing_client()
        token = client.get("/api/auth/csrf/").data["csrf_token"]

        response = client.post(
            "/api/auth/logout/", HTTP_X_CSRFTOKEN=token
        )

        self.assertEqual(
            response.status_code,
            204,
            "the token from /api/auth/csrf/ was rejected by CSRF middleware",
        )

    def test_mutating_request_without_token_is_rejected(self):
        """The counterpart, so the test above cannot pass vacuously.

        This is the assertion that failed when the token was read from
        `document.cookie`: on a real deployment the header went out unset and
        every write failed exactly like this.
        """
        client = self._enforcing_client()
        client.get("/api/auth/csrf/")  # set the cookie...

        response = client.post("/api/auth/logout/")  # ...but send no header

        self.assertEqual(
            response.status_code,
            403,
            "a request with no X-CSRFToken was accepted; the positive test "
            "above would then prove nothing",
        )

    def test_register_creates_profile(self):
        self.client.post(
            "/api/auth/register/",
            {
                "email": "profile@example.com",
                "password": "sup3r-secret-pw",
            },
            content_type="application/json",
        )

        user = User.objects.get(email="profile@example.com")
        self.assertTrue(hasattr(user, "profile"))

    def test_register_rejects_duplicate_email(self):
        User.objects.create_user(
            username="dupe@example.com",
            email="dupe@example.com",
            password="sup3r-secret-pw",
        )

        response = self.client.post(
            "/api/auth/register/",
            {
                "email": "dupe@example.com",
                "password": "sup3r-secret-pw",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_register_rejects_weak_password(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "email": "weak@example.com",
                "password": "123",
            },
            content_type="application/json",
        )


class LoginTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="login@example.com",
            email="login@example.com",
            password="sup3r-secret-pw",
        )

    def test_login_with_valid_credentials(self):
        response = self.client.post(
            "/api/auth/login/",
            {
                "email": "login@example.com",
                "password": "sup3r-secret-pw",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["email"], "login@example.com")

    def test_login_with_wrong_password_is_rejected(self):
        response = self.client.post(
            "/api/auth/login/",
            {
                "email": "login@example.com",
                "password": "wrong-password",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_login_is_case_insensitive_on_email(self):
        response = self.client.post(
            "/api/auth/login/",
            {
                "email": "LOGIN@example.com",
                "password": "sup3r-secret-pw",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

    def test_logout_ends_the_session(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/api/auth/me/").data["authenticated"], True)

        self.client.post("/api/auth/logout/")

        self.assertEqual(self.client.get("/api/auth/me/").data["authenticated"], False)


class MeEndpointTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="me@example.com",
            email="me@example.com",
            password="sup3r-secret-pw",
        )

    def test_me_is_unauthenticated_when_anonymous(self):
        response = self.client.get("/api/auth/me/")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["authenticated"])
        self.assertIsNone(response.data["user"])

    def test_me_returns_the_signed_in_user(self):
        self.client.force_login(self.user)

        response = self.client.get("/api/auth/me/")

        self.assertTrue(response.data["authenticated"])
        self.assertEqual(response.data["user"]["email"], "me@example.com")

    def test_me_exposes_master_resume_and_job_counts(self):
        self.client.force_login(self.user)

        payload = self.client.get("/api/auth/me/").data["user"]

        self.assertIn("has_master_resume", payload)
        self.assertIn("job_count", payload)
        self.assertFalse(payload["has_master_resume"])
        self.assertEqual(payload["job_count"], 0)


class ProfileEndpointTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="settings@example.com",
            email="settings@example.com",
            password="sup3r-secret-pw",
        )

    def test_profile_requires_authentication(self):
        response = self.client.get("/api/auth/profile/")

        self.assertIn(response.status_code, [401, 403])

    def test_profile_can_be_updated(self):
        self.client.force_login(self.user)

        response = self.client.patch(
            "/api/auth/profile/",
            {"headline": "Backend Engineer", "discipline": "ENGINEER"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["headline"], "Backend Engineer")
