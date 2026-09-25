import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserProfile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "headline",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Short role summary shown on the dashboard.",
                        max_length=150,
                    ),
                ),
                (
                    "discipline",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("ENGINEER", "Engineering"),
                            ("DESIGNER", "Design"),
                            ("PRODUCT", "Product"),
                            ("DATA", "Data & Analytics"),
                            ("MARKETING", "Marketing"),
                            ("OTHER", "Other"),
                        ],
                        default="",
                        max_length=32,
                    ),
                ),
                (
                    "target_locations",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text=(
                            "Comma-separated list of preferred locations."
                        ),
                        max_length=255,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"abstract": False},
        ),
    ]
