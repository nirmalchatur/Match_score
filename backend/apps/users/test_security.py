"""
Tests for the security page: sessions, revocation, password change, events.

The properties that matter, in order of severity if broken:

1. A signed-in user cannot see or revoke another account's sessions or events.
2. Revoking other sessions does not revoke the caller's own.
3. A password change requires the current password and keeps the caller signed
   in.

Everything else is plumbing. These three are why the file exists.
"""

from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.test import TestCase
from rest_framework.test import APIClient

from .security import (
    SecurityEvent,
    change_password,
    list_sessions,
    revoke_other_sessions,
)

User = get_user_model()


def make_user(username, password="test-password-123"):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password=password,
    )


def login_session(user):
    """A real authenticated session row, as the login view would create."""
    store = SessionStore()
    store[SESSION_KEY] = str(user.pk)
    store[BACKEND_KEY] = "django.contrib.auth.backends.ModelBackend"
    store[HASH_KEY] = user.get_session_auth_hash()
    store.create()
    return store.session_key


# Imported by name from django.contrib.auth to avoid hardcoding the string keys,
# which have been stable for a decade but are still not ours to guess.
from django.contrib.auth import (  # noqa: E402
    BACKEND_SESSION_KEY,
    HASH_SESSION_KEY,
    SESSION_KEY,
)

BACKEND_KEY = BACKEND_SESSION_KEY
HASH_KEY = HASH_SESSION_KEY


class SecurityEventTests(TestCase):
    def setUp(self):
        self.user = make_user("alice")

    def test_record_creates_row(self):
        SecurityEvent.record(self.user, SecurityEvent.LOGIN_SUCCESS)
        self.assertEqual(SecurityEvent.objects.filter(user=self.user).count(), 1)

    def test_record_ignores_anonymous(self):
        from django.contrib.auth.models import AnonymousUser

        SecurityEvent.record(AnonymousUser(), SecurityEvent.LOGIN_SUCCESS)
        self.assertEqual(SecurityEvent.objects.count(), 0)

    def test_record_never_raises_on_a_bad_user(self):
        class Exploding:
            pk = 1
            is_authenticated = True

            def __getattr__(self, name):
                raise RuntimeError("boom")

        SecurityEvent.record(Exploding(), SecurityEvent.LOGIN_SUCCESS)

    def test_label_falls_back_for_unknown_event(self):
        row = SecurityEvent(user=self.user, event="NOT_A_REAL_EVENT")
        self.assertEqual(row.label, "NOT_A_REAL_EVENT")

    def test_user_agent_is_truncated(self):
        request = type("R", (), {"META": {"HTTP_USER_AGENT": "x" * 5000}})()
        SecurityEvent.record(self.user, SecurityEvent.LOGIN_SUCCESS, request=request)
        row = SecurityEvent.objects.get(user=self.user)
        self.assertLessEqual(len(row.user_agent), 300)


class SessionListingTests(TestCase):
    def setUp(self):
        self.user = make_user("alice")
        self.other = make_user("bob")

    def test_lists_only_my_sessions(self):
        mine = login_session(self.user)
        login_session(self.other)

        rows = list_sessions(self.user)

        self.assertEqual([r["key"] for r in rows], [mine])

    def test_marks_the_current_session(self):
        first = login_session(self.user)
        second = login_session(self.user)

        rows = list_sessions(self.user, current_session_key=second)

        by_key = {r["key"]: r for r in rows}
        self.assertTrue(by_key[second]["is_current"])
        self.assertFalse(by_key[first]["is_current"])

    def test_expired_sessions_are_not_listed(self):
        from django.contrib.sessions.models import Session
        from django.utils import timezone

        key = login_session(self.user)

        # Updated through the model rather than by setting ``store.expire_date``
        # and calling save(): SessionStore.save() recomputes expire_date from
        # the session's own age, so the assignment is silently undone and the
        # test would assert the opposite of what it names.
        Session.objects.filter(session_key=key).update(
            expire_date=timezone.now() - timezone.timedelta(days=1)
        )

        self.assertEqual(list_sessions(self.user), [])

    def test_never_returns_the_session_payload(self):
        login_session(self.user)
        row = list_sessions(self.user)[0]
        # The decoded payload holds the auth hash. Leaking it would leak the
        # credential, so the response shape must not contain it.
        self.assertNotIn("data", row)
        self.assertNotIn("_auth_user_hash", str(row))


class RevokeSessionTests(TestCase):
    def setUp(self):
        self.user = make_user("alice")
        self.other = make_user("bob")

    def test_revokes_other_sessions_but_keeps_the_named_one(self):
        keep = login_session(self.user)
        stale = login_session(self.user)

        removed = revoke_other_sessions(self.user, keep_session_key=keep)

        self.assertEqual(removed, 1)
        remaining = {r["key"] for r in list_sessions(self.user)}
        self.assertEqual(remaining, {keep})
        self.assertNotIn(stale, remaining)

    def test_never_revokes_another_accounts_sessions(self):
        mine = login_session(self.user)
        theirs = login_session(self.other)

        revoke_other_sessions(self.user, keep_session_key=mine)

        self.assertIn(theirs, {r["key"] for r in list_sessions(self.other)})

    def test_blank_keep_key_revokes_everything_for_that_account(self):
        login_session(self.user)
        login_session(self.user)

        removed = revoke_other_sessions(self.user)

        self.assertEqual(removed, 2)
        self.assertEqual(list_sessions(self.user), [])


class ChangePasswordTests(TestCase):
    def setUp(self):
        self.user = make_user("alice", password="original-password-1")
        self.client = APIClient()
        self.client.force_login(self.user)

    def _change(self, current, new):
        return self.client.post(
            "/api/auth/security/password/",
            {"current_password": current, "new_password": new},
            format="json",
        )

    def test_requires_authentication(self):
        anonymous = APIClient()
        self.assertIn(
            anonymous.post(
                "/api/auth/security/password/",
                {
                    "current_password": "original-password-1",
                    "new_password": "brand-new-99",
                },
                format="json",
            ).status_code,
            (401, 403),
        )

    def test_rejects_a_wrong_current_password(self):
        # Without this check, anyone who finds an unlocked browser session
        # could set a new password and take the account over permanently.
        response = self._change("not-the-password", "brand-new-99")
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("original-password-1"))

    def test_changes_the_password(self):
        self.assertEqual(
            self._change("original-password-1", "brand-new-99").status_code, 200
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("brand-new-99"))

    def test_keeps_the_current_session_signed_in(self):
        # The behaviour that stops a password change looking like a failure:
        # the caller stays signed in on the tab they changed it from.
        self._change("original-password-1", "brand-new-99")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)

    def test_records_a_security_event(self):
        self._change("original-password-1", "brand-new-99")
        self.assertTrue(
            SecurityEvent.objects.filter(
                user=self.user, event=SecurityEvent.PASSWORD_CHANGED
            ).exists()
        )

    def test_rejects_a_password_that_fails_validation(self):
        self.assertEqual(self._change("original-password-1", "123").status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("original-password-1"))

    def test_rejects_identical_passwords(self):
        response = self._change("original-password-1", "original-password-1")
        self.assertEqual(response.status_code, 400)


class SecurityApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user("alice")
        self.other = make_user("bob")
        self.client.force_login(self.user)

    def test_overview_requires_authentication(self):
        anonymous = APIClient()
        self.assertIn(anonymous.get("/api/auth/security/").status_code, (401, 403))

    def test_overview_returns_sessions_and_events(self):
        SecurityEvent.record(self.user, SecurityEvent.LOGIN_SUCCESS)
        response = self.client.get("/api/auth/security/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("sessions", response.data)
        self.assertIn("events", response.data)

    def test_overview_never_shows_another_accounts_events(self):
        SecurityEvent.record(self.other, SecurityEvent.LOGIN_SUCCESS)
        response = self.client.get("/api/auth/security/")
        self.assertEqual(response.data["events"], [])

    def test_revoke_requires_authentication(self):
        anonymous = APIClient()
        self.assertIn(
            anonymous.post("/api/auth/security/revoke-others/").status_code,
            (401, 403),
        )

    def test_revoke_keeps_the_caller_signed_in(self):
        # The endpoint acts "everywhere else". If it also killed the caller's
        # own session, pressing the button would sign the user out, which is
        # the opposite of what the label says.
        self.assertEqual(
            self.client.post("/api/auth/security/revoke-others/").status_code, 200
        )
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)

    def test_revoke_removes_a_second_real_session(self):
        login_session(self.user)
        response = self.client.post("/api/auth/security/revoke-others/")
        self.assertEqual(response.data["revoked"], 1)

    def test_revoke_leaves_another_account_alone(self):
        theirs = login_session(self.other)
        self.client.post("/api/auth/security/revoke-others/")
        self.assertIn(theirs, {r["key"] for r in list_sessions(self.other)})

    def test_login_is_recorded(self):
        # A dedicated client with no prior session. ``setUp`` force-logs the
        # test client in, and reusing that client here would test the
        # already-authenticated path rather than the login view.
        #
        # The project uses Django's default User, whose USERNAME_FIELD is
        # ``username``, so the login view authenticates on the email-shaped
        # username. The helper therefore creates the account with the email
        # address as the username, which is what registration does.
        account = User.objects.create_user(
            username="login-probe@example.com",
            email="login-probe@example.com",
            password="test-password-123",
        )

        fresh = APIClient()
        response = fresh.post(
            "/api/auth/login/",
            {"email": "login-probe@example.com", "password": "test-password-123"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            SecurityEvent.objects.filter(
                user=account, event=SecurityEvent.LOGIN_SUCCESS
            ).exists()
        )

