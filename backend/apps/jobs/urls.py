from django.urls import path

from .views import JobMatchView, JobListView, JobDetailView


urlpatterns = [
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