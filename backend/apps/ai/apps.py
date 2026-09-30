from django.apps import AppConfig


class AiConfig(AppConfig):
    """
    The AI boundary: provider abstraction, orchestration, schemas, validators.

    It became an installed app when :class:`apps.ai.models.AIRun` landed. The
    module tree already existed as plain packages -- which is why the provider
    abstraction works without an app -- but Django only creates a table for a
    model in an installed app, and an audit trail with no table is a comment.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ai"
    label = "ai"
    verbose_name = "AI"
