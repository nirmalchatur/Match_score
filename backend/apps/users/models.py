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
