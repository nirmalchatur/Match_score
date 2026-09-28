"""
Tests for per-user provider selection.

The interesting cases are all about *not* sending a resume somewhere the user
did not ask for. Each test below pins one branch of that decision, because the
failure is silent and privacy-relevant rather than a crash.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.ai import selection
from apps.users.models import ProviderCredential, UserProfile

User = get_user_model()


class ProviderSelectionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="sel@example.com", email="sel@example.com", password="pw"
        )
        UserProfile.objects.get_or_create(user=self.user)

    def _choose(self, slug: str):
        profile = self.user.profile
        profile.ai_setup = slug
        profile.save(update_fields=["ai_setup"])

    def _add_gemini_key(self):
        # Matches how the app itself stores one: set_key() encrypts, save()
        # persists. Building encrypted_key by hand would test a shape the
        # application never creates.
        credential = ProviderCredential(user=self.user, provider="gemini")
        credential.set_key("AIzaSyFAKEFAKEFAKEFAKEFAKEFAKEFAKE")
        credential.save()

    # --- no explicit choice ------------------------------------------------

    @override_settings(AI_PROVIDER="gemini")
    def test_no_choice_uses_deployment_default(self):
        self.assertEqual(selection.resolve_provider_name(self.user), ("gemini", "default"))

    @override_settings(AI_PROVIDER="ollama")
    def test_no_choice_follows_a_local_deployment(self):
        self.assertEqual(selection.resolve_provider_name(self.user), ("ollama", "default"))

    # --- local ollama ------------------------------------------------------

    @override_settings(AI_PROVIDER="ollama")
    def test_ollama_choice_is_honoured(self):
        """The point of the feature: a local deployment stays local, and a
        user who picked it is not quietly moved to a hosted model."""
        self._choose("ollama")
        self.assertEqual(selection.resolve_provider_name(self.user), ("ollama", "user_choice"))

    @override_settings(AI_PROVIDER="ollama")
    def test_ollama_needs_no_key(self):
        """Ollama is keyless, so choosing it must not require a credential."""
        self._choose("ollama")
        name, _ = selection.resolve_provider_name(self.user)
        self.assertEqual(name, "ollama")

    @override_settings(AI_PROVIDER="gemini")
    def test_ollama_choice_on_a_hosted_deployment_falls_back_and_says_so(self):
        """A local daemon is a server-side fact. If the deployment is not
        pointed at one, honouring the choice would produce a connection error
        rather than an answer, so it falls back and reports why."""
        self._choose("ollama")
        self.assertEqual(
            selection.resolve_provider_name(self.user), ("gemini", "choice_unavailable")
        )

    # --- hosted gemini -----------------------------------------------------

    @override_settings(AI_PROVIDER="ollama")
    def test_gemini_choice_with_a_key_wins_over_a_local_default(self):
        """A stored key is what makes Gemini usable without server config, so
        an explicit choice plus a credential overrides the deployment default."""
        self._choose("gemini")
        self._add_gemini_key()
        self.assertEqual(selection.resolve_provider_name(self.user), ("gemini", "user_choice"))

    @override_settings(AI_PROVIDER="ollama")
    def test_gemini_choice_without_a_key_does_not_switch(self):
        """The critical safety case. Having *chosen* Gemini is not enough; the
        request needs a key. Without one we keep the deployment default rather
        than sending resume text to a provider the request cannot authenticate
        to anyway."""
        self._choose("gemini")
        self.assertEqual(
            selection.resolve_provider_name(self.user), ("ollama", "missing_key")
        )

    @override_settings(AI_PROVIDER="ollama")
    def test_a_key_alone_never_switches_provider(self):
        """A stored credential must not, by itself, move someone's resume off
        the local model. The user has to have chosen it. This is the single
        most privacy-relevant assertion in the file."""
        self._add_gemini_key()
        self.assertEqual(selection.resolve_provider_name(self.user), ("ollama", "default"))

    # --- robustness --------------------------------------------------------

    @override_settings(AI_PROVIDER="gemini")
    def test_unknown_slug_is_ignored(self):
        """A value that is not a selectable provider must not reach the
        registry lookup, which would surface as a 500."""
        self._choose("not-a-provider")
        self.assertEqual(selection.resolve_provider_name(self.user), ("gemini", "default"))

    @override_settings(AI_PROVIDER="")
    def test_unconfigured_deployment_still_reports_empty(self):
        self._choose("gemini")
        self._add_gemini_key()
        name, reason = selection.resolve_provider_name(self.user)
        self.assertIn(name, ("", "gemini"))
        self.assertIn(reason, ("user_choice", "default", "missing_key"))

    def test_default_provider_name_normalises(self):
        with override_settings(AI_PROVIDER="  Gemini  "):
            self.assertEqual(selection.default_provider_name(), "gemini")
