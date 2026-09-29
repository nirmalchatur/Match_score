from django.urls import path

from .views import (
    NotificationListView,
    NotificationPreferenceView,
    NotificationReadAllView,
    NotificationReadView,
)


urlpatterns = [
    # Declared before "<int:pk>/" so the literal paths are not swallowed by it.
    path(
        "read-all/",
        NotificationReadAllView.as_view(),
        name="notification-read-all",
    ),
    path(
        "preferences/",
        NotificationPreferenceView.as_view(),
        name="notification-preferences",
    ),
    path(
        "",
        NotificationListView.as_view(),
        name="notification-list",
    ),
    path(
        "<int:pk>/read/",
        NotificationReadView.as_view(),
        name="notification-read",
    ),
]
