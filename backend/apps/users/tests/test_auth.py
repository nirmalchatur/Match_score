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
