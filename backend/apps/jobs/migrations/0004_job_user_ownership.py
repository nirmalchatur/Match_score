"""
Attach every pre-existing Job to an account.

TailorUp introduced per-account ownership. Existing rows were created
before accounts existed, so they are claimed by a single "legacy" holder
rather than deleted. This keeps all historical analyses intact and visible
instead of orphaning them.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

LEGACY_EMAIL = "legacy@tailorup.local"


def _legacy_user(apps):
    """Return the account that owns pre-TailorUp rows, creating it if needed.

    Uses the historical model registry so the migration is not coupled to
    the live model definition.
    """
    User = apps.get_model(settings.AUTH_USER_MODEL)

    user, _ = User.objects.get_or_create(
        username=LEGACY_EMAIL,
        defaults={
            "email": LEGACY_EMAIL,
            # A leading "!" marks the password as unusable in Django, so
            # this account can never be signed into until claimed manually.
            "password": "!unusable-legacy-account",
        },
    )
    return user


def assign_legacy_owner(apps, schema_editor):
    user = _legacy_user(apps)
    apps.get_model("jobs", "Job").objects.filter(
        user__isnull=True
    ).update(
        user=user
    )


def clear_owner(apps, schema_editor):
    apps.get_model("jobs", "Job").objects.filter(
        user__email=LEGACY_EMAIL
    ).update(
        user=None
    )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("jobs", "0003_job_error_message_job_pipeline_steps_and_more"),
    ]

    operations = [
        # 1. Add nullable so existing rows are untouched.
        migrations.AddField(
            model_name="job",
            name="user",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="jobs",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        # 2. Backfill before enforcing the constraint.
        migrations.RunPython(assign_legacy_owner, clear_owner),
        # 3. Enforce ownership.
        migrations.AlterField(
            model_name="job",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="jobs",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        # 4. URL uniqueness is now per account, not global.
        migrations.AlterField(
            model_name="job",
            name="url",
            field=models.URLField(),
        ),
        migrations.AddConstraint(
            model_name="job",
            constraint=models.UniqueConstraint(
                fields=("user", "url"),
                name="unique_job_url_per_user",
            ),
        ),
        migrations.AlterModelOptions(
            name="job",
            options={"ordering": ["-created_at"]},
        ),
    ]
