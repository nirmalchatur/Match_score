from django.apps import AppConfig


class CommonConfig(AppConfig):
    """
    Shared, app-agnostic pieces that cannot belong to one feature.

    It became an installed app when the activity record landed
    (``apps.common.models.ActivityEvent``): the record is written *by* resumes,
    jobs, applications and the AI layer, so putting it in any one of them would
    have made the others depend on that app's model module. Django discovers
    models only through ``INSTALLED_APPS``, so the app has to be listed there
    for the table to exist at all.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"
    label = "common"
    verbose_name = "Common"
