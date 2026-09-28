"""
Tests for user-supplied AI provider credentials.

The property under test throughout: **a stored key is never disclosed.** That
is asserted from every angle available -- the database column, the API
responses, the error text, and the prompt payload -- because a leak only has
to happen once in any one of them.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.ai.exceptions import AIProviderUnavailableError
from apps.ai.providers.base import TailoringRequest
from apps.ai.providers.gemini import GeminiProvider
from apps.users.crypto import CredentialCryptoError, decrypt, encrypt, mask
from apps.users.models import ProviderCredential

User = get_user_model()

#: A realistic-looking but entirely fictional Gemini key.
FAKE_KEY = "AIzaSyD-EXAMPLE0000000000000000000000000000000000abcd"
OTHER_KEY = "AIzaSyD-DIFFERENT00000000000000000000000000000wxyz"


class CredentialCryptoTests(TestCase):
    """The encryption primitive itself."""

    def test_round_trip(self):
        self.assertEqual(decrypt(encrypt(FAKE_KEY)), FAKE_KEY)

    def test_ciphertext_does_not_contain_the_plaintext(self):
        """The stored value must not be the key in any recoverable form."""
        token = encrypt(FAKE_KEY)
        self.assertNotIn(FAKE_KEY, token)
        self.assertNotIn(FAKE_KEY[8:20], token)
        self.assertNotIn(FAKE_KEY[-8:], token)

    def test_ciphertext_differs_each_time(self):
        """Fernet includes a random IV, so identical keys must not collide.

        Without this, two users with the same key would have identical rows and
        a leak would identify them.
        """
        self.assertNotEqual(encrypt(FAKE_KEY), encrypt(FAKE_KEY))

    def test_tampered_ciphertext_raises(self):
        token = encrypt(FAKE_KEY)
        tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
        with self.assertRaises(CredentialCryptoError):
            decrypt(tampered)

    def test_garbage_raises_rather_than_returning_junk(self):
        with self.assertRaises(CredentialCryptoError):
            decrypt("not-a-fernet-token")

    def test_rotating_secret_key_makes_it_undecryptable(self):
        """Documented consequence: keys must be re-pasted after a rotation.

        Asserted so the behaviour is a deliberate contract rather than a
        surprise discovered during an incident. The token is minted *before*
        the override -- encrypting inside it would use the new key on both
        sides and pass without proving anything.
        """
        token = encrypt(FAKE_KEY)

        with override_settings(SECRET_KEY="a-completely-different-secret"):
            with self.assertRaises(CredentialCryptoError):
                decrypt(token)
class ProviderCredentialModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="owner@example.com", email="owner@example.com", password="pw"
        )
        self.credential = ProviderCredential(user=self.user, provider="gemini")
        self.credential.set_key(FAKE_KEY)
        self.credential.save()

    def test_plaintext_is_not_stored(self):
        """The single most important assertion in this file."""
        from_db = ProviderCredential.objects.get(pk=self.credential.pk)
        self.assertNotIn(FAKE_KEY, from_db.encrypted_key)
        self.assertNotEqual(from_db.encrypted_key, FAKE_KEY)

    def test_reveal_returns_the_original(self):
        self.assertEqual(self.credential.reveal_key(), FAKE_KEY)

    def test_public_dict_cannot_reconstruct_the_key(self):
        public = self.credential.public_dict()
        self.assertNotIn("api_key", public)
        self.assertNotIn("encrypted_key", public)
        # 4 + 4 characters is not enough to recover a 39-character key.
        self.assertEqual(len(public["key_hint"].replace("...", "")), 8)

    def test_set_key_replaces_the_previous_one(self):
        self.credential.set_key(OTHER_KEY)
        self.credential.save()
        self.credential.refresh_from_db()
        self.assertEqual(self.credential.reveal_key(), OTHER_KEY)

    def test_one_row_per_user_per_provider(self):
        again, created = ProviderCredential.objects.get_or_create(
            user=self.user,
            provider="gemini",
            defaults={"encrypted_key": "x"},
        )
        self.assertFalse(created)
        self.assertEqual(again.pk, self.credential.pk)
        self.assertEqual(ProviderCredential.objects.count(), 1)

    def test_reveal_deletes_an_undecryptable_row(self):
        """An undecryptable key must not linger looking 'configured'."""
        self.credential.encrypted_key = "corrupted-token"
        self.credential.save()

        with self.assertRaises(CredentialCryptoError):
            self.credential.reveal_key()

        self.assertFalse(
            ProviderCredential.objects.filter(pk=self.credential.pk).exists()
        )


class ProviderCredentialApiTests(TestCase):
    """GET/POST/DELETE /api/auth/ai-key/"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="u@example.com", email="u@example.com", password="password123"
        )
        self.other = User.objects.create_user(
            username="o@example.com", email="o@example.com", password="password123"
        )
        self.url = reverse("auth-ai-key")
        self.client.force_login(self.user)

    def _post(self, key, **extra):
        return self.client.post(
            self.url, {"provider": "gemini", "api_key": key, **extra}
        )
    # -- storage and disclosure -------------------------------------------

    def test_saving_reports_configured_without_the_key(self):
        response = self._post(FAKE_KEY)
        self.assertEqual(response.status_code, 201)
        body = response.content.decode()
        self.assertNotIn(FAKE_KEY, body)
        self.assertNotIn(FAKE_KEY[10:-6], body)
        self.assertTrue(response.json()["configured"])

    def test_get_before_and_after_saving(self):
        before = self.client.get(self.url).json()
        self.assertFalse(before["configured"])
        self.assertNotIn("key_hint", before)

        self._post(FAKE_KEY)

        after = self.client.get(self.url).json()
        self.assertTrue(after["configured"])
        self.assertIn("key_hint", after)

    def test_no_method_ever_returns_the_key(self):
        """Sweep every verb against a configured account."""
        self._post(FAKE_KEY)
        for response in (
            self.client.get(self.url),
            self.client.get(self.url, {"provider": "gemini"}),
            self.client.options(self.url),
        ):
            self.assertNotIn(FAKE_KEY, response.content.decode())

    def test_delete_removes_it(self):
        self._post(FAKE_KEY)
        response = self.client.delete(self.url, {"provider": "gemini"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["configured"])
        self.assertFalse(ProviderCredential.objects.exists())

    def test_delete_is_idempotent(self):
        """Deleting when nothing is stored is not an error."""
        response = self.client.delete(self.url, {"provider": "gemini"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["configured"])

    def test_saving_twice_updates_in_place(self):
        self._post(FAKE_KEY)
        self._post(OTHER_KEY)
        self.assertEqual(ProviderCredential.objects.count(), 1)
        self.assertEqual(ProviderCredential.objects.get().reveal_key(), OTHER_KEY)

    # -- isolation ---------------------------------------------------------

    def test_requires_authentication(self):
        self.client.logout()
        for response in (
            self.client.get(self.url),
            self._post(FAKE_KEY),
            self.client.delete(self.url),
        ):
            self.assertIn(response.status_code, (401, 403))

    def test_another_user_cannot_see_or_delete_this_key(self):
        self._post(FAKE_KEY)
        self.client.force_login(self.other)

        self.assertFalse(self.client.get(self.url).json()["configured"])

        self.client.delete(self.url, {"provider": "gemini"})

        self.assertTrue(
            ProviderCredential.objects.filter(user=self.user).exists(),
            "one user's delete must not touch another's key",
        )

    # -- validation --------------------------------------------------------

    def test_rejects_a_url_instead_of_a_key(self):
        response = self._post("https://aistudio.google.com/apikey")
        self.assertEqual(response.status_code, 400)
        self.assertIn("URL", str(response.json()).upper())

    def test_rejects_an_obviously_short_key(self):
        self.assertEqual(self._post("abc").status_code, 400)

    def test_rejects_an_unknown_provider(self):
        response = self._post(FAKE_KEY, provider="not-a-provider")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ProviderCredential.objects.exists())

    def test_rejects_a_key_containing_whitespace(self):
        """A copy-paste often brings a newline along."""
        response = self._post(FAKE_KEY + "\n")
        self.assertEqual(response.status_code, 400)
        self.assertIn("space", str(response.json()).lower())


class LogoutDeletesCredentialTests(TestCase):
    """Signing out must leave no credential behind."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="u@example.com", email="u@example.com", password="password123"
        )
        self.other = User.objects.create_user(
            username="o@example.com", email="o@example.com", password="password123"
        )

    def _store(self, user, key=FAKE_KEY):
        credential = ProviderCredential(user=user, provider="gemini")
        credential.set_key(key)
        credential.save()
        return credential

    def test_logout_deletes_the_callers_key(self):
        credential = self._store(self.user)
        self.client.force_login(self.user)

        response = self.client.post("/api/auth/logout/")

        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            ProviderCredential.objects.filter(pk=credential.pk).exists(),
            "the key must be gone, not merely forgotten",
        )

    def test_logout_keeps_other_users_keys(self):
        """The exact scope of the delete, which is easy to over-reach."""
        theirs = self._store(self.other)
        self._store(self.user)

        self.client.force_login(self.user)
        self.client.post("/api/auth/logout/")

        self.assertTrue(
            ProviderCredential.objects.filter(pk=theirs.pk).exists(),
            "logging out one user must not delete another user's key",
        )

    def test_logout_without_a_key_is_unaffected(self):
        self.client.force_login(self.user)
        response = self.client.post("/api/auth/logout/")
        self.assertEqual(response.status_code, 204)

    def test_anonymous_logout_succeeds_and_deletes_nothing(self):
        """A stray POST from a logged-out tab must not be an error."""
        theirs = self._store(self.other)

        response = self.client.post("/api/auth/logout/")

        self.assertEqual(response.status_code, 204)
        self.assertTrue(ProviderCredential.objects.filter(pk=theirs.pk).exists())


class GeminiKeyUsageTests(TestCase):
    """The key reaches the provider and goes nowhere else."""

    def _request(self, key=""):
        return TailoringRequest(resume={"x": 1}, job={"y": 2}, api_key=key)

    def test_provider_reads_the_key_from_the_request(self):
        self.assertEqual(
            GeminiProvider()._key_for(self._request(FAKE_KEY)), FAKE_KEY
        )

    def test_blank_and_whitespace_keys_are_treated_as_absent(self):
        provider = GeminiProvider()
        for value in ("", "   ", None, "\n"):
            self.assertEqual(provider._key_for(self._request(value)), "")

    def test_no_key_raises_a_clear_error(self):
        with self.assertRaises(AIProviderUnavailableError) as ctx:
            GeminiProvider().tailor_resume(self._request())
        self.assertIn("Settings", ctx.exception.message)

    def test_the_key_never_enters_the_prompt_payload(self):
        """The payload is serialised into prompts and sent to the provider."""
        payload = self._request(FAKE_KEY).to_payload()
        self.assertNotIn("api_key", payload)
        self.assertNotIn(FAKE_KEY, str(payload))

    def test_describe_reports_that_a_user_key_is_needed(self):
        described = GeminiProvider().describe()
        self.assertTrue(described["requires_user_key"])
        self.assertFalse(described["server_key_configured"])
        self.assertNotIn(FAKE_KEY, str(described))

    def test_health_points_at_settings_not_a_server_variable(self):
        available, message = GeminiProvider().health()
        self.assertFalse(available)
        self.assertIn("Settings", message)
        # The old wording told users to set a server variable. That is gone.
        self.assertNotIn("GEMINI_API_KEY", message)

