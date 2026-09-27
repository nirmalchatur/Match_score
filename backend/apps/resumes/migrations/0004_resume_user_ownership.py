"""
Attach every pre-existing Resume to an account.

Same data-preserving approach as the jobs migration: existing resumes are
claimed by a single "legacy" holder rather than deleted, so no uploaded
document is lost during the move to per-account ownership.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

LEGACY_EMAIL = "legacy@tailorup.local"


def _legacy_user(apps):
    User = apps.get_model(settings.AUTH_USER_MODEL)

    user, _ = User.objects.get_or_create(
        username=LEGACY_EMAIL,
        defaults={
            "email": LEGACY_EMAIL,
            "password": "!unusable-legacy-account",
        },
    )
    return user


def assign_legacy_owner(apps, schema_editor):
    user = _legacy_user(apps)
    apps.get_model("resumes", "Resume").objects.filter(
        user__isnull=True
    ).update(
        user=user
    )


def clear_owner(apps, schema_editor):
    apps.get_model("resumes", "Resume").objects.filter(
        user__email=LEGACY_EMAIL
    ).update(
        user=None
    )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("resumes", "0003_resume_profile_data"),
    ]

    operations = [
        migrations.AddField(
            model_name="resume",
            name="user",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="resumes",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(assign_legacy_owner, clear_owner),
        migrations.AlterField(
            model_name="resume",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="resumes",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
