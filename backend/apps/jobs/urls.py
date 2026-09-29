from django.urls import path

from .views import (
    JobAnalyzeView,
    JobMatchView,
    JobListView,
    JobDetailView,
    JobSearchView,
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
    # Declared before "<int:pk>/" so "search" is not parsed as a job id.
    path(
        "search/",
        JobSearchView.as_view(),
        name="job-search",
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