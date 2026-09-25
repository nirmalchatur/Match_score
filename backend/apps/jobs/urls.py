from django.urls import path

from .views import (
    JobAnalyzeView,
    JobMatchView,
    JobListView,
    JobDetailView,
)


urlpatterns = [
    path(
        "analyze/",
        JobAnalyzeView.as_view(),
        name="job-analyze",
    ),
    path(
        "match/",
        JobMatchView.as_view(),
        name="job-match",
    ),
    path(
        "",
        JobListView.as_view(),
        name="job-list",
    ),
    path(
        "<int:pk>/",
        JobDetailView.as_view(),
        name="job-detail",
    ),
]