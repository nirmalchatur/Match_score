"""
Per-user settings that are not part of Django's built-in auth model.

We deliberately reuse ``django.contrib.auth.models.User`` for identity
(authentication already ships with Django and is installed), and keep
TailorUp-specific preferences in a 1:1 profile so a future custom user
model swap stays a contained change.
"""

from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    """Workspace-level settings for a TailorUp account."""

    DISCIPLINE_CHOICES = [
        ("ENGINEER", "Engineering"),
        ("DESIGNER", "Design"),
        ("PRODUCT", "Product"),
        ("DATA", "Data & Analytics"),
        ("MARKETING", "Marketing"),
        ("OTHER", "Other"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )

    headline = models.CharField(
        max_length=150,
        blank=True,
        default="",
        help_text="Short role summary shown on the dashboard.",
    )

    discipline = models.CharField(
        max_length=32,
        choices=DISCIPLINE_CHOICES,
        blank=True,
        default="",
    )

    target_locations = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Comma-separated list of preferred locations.",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile - {self.user.email}"


class ProviderCredential(models.Model):
    """A user's own third-party API key, stored encrypted.

    One row per (user, provider). The plaintext key is never stored, never
    returned by an API, and never logged -- ``encrypted_key`` holds a Fernet
    token produced by :mod:`apps.users.crypto`.

    ``key_hint`` is a masked prefix/suffix kept alongside purely so the UI can
    show *which* key is stored ("AIza...4f2b") to help someone juggling more
    than one. It is written once, at save time, and is not a secret.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="provider_credentials",
    )

    provider = models.CharField(
        max_length=32,
        help_text="Provider slug, e.g. 'gemini'.",
    )

    encrypted_key = models.TextField(
        help_text="Fernet token. Never the plaintext key.",
    )

    key_hint = models.CharField(
        max_length=16,
        blank=True,
        default="",
        help_text="Masked hint such as 'AIza...4f2b'. Not a secret.",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # A user holds at most one key per provider, which lets the save path
        # be an unconditional update rather than a lookup-then-branch.
        constraints = [
            models.UniqueConstraint(
                fields=["user", "provider"],
                name="uniq_user_provider_credential",
            ),
        ]

    def __str__(self):
        return f"{self.provider} credential for {self.user.email}"

    def set_key(self, plaintext: str) -> None:
        """Store a new plaintext key: encrypt it and refresh the hint."""
        from .crypto import encrypt, mask

        self.encrypted_key = encrypt(plaintext)
        self.key_hint = mask(plaintext)

    def reveal_key(self) -> str:
        """Decrypt for immediate use. Never for an API response or a log."""
        from .crypto import CredentialCryptoError, decrypt

        try:
            return decrypt(self.encrypted_key)
        except CredentialCryptoError:
            # A key that cannot be decrypted is worse than no key: it looks
            # configured but silently fails at call time. Dropping it lets the
            # user re-paste and see an honest "not configured".
            self.delete()
            raise

    def public_dict(self) -> dict:
        """The only shape any endpoint is allowed to return.

        Note there is no field here from which the key could be recovered:
        ``key_hint`` is a 4+4 character mask, not a prefix that scales.
        """
        return {
            "provider": self.provider,
            "configured": True,
            "key_hint": self.key_hint,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

