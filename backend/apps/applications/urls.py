from django.urls import path

from .views import (
    ApplicationDetailView,
    DashboardStatsView,
    ApplicationListView,
    ApplicationStatusView,
)


urlpatterns = [

    path(
        "",
        ApplicationListView.as_view(),
        name="application-list",
    ),

    path(
        "dashboard/",
        DashboardStatsView.as_view(),
        name="application-dashboard",
    ),

    path(
        "<int:pk>/",
        ApplicationDetailView.as_view(),
        name="application-detail",
    ),

    path(
        "<int:pk>/status/",
        ApplicationStatusView.as_view(),
        name="application-status",
    ),

]
