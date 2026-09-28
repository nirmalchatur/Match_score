from django.urls import path

from .views import (
    AIProviderStatusView,
    QualitiesView,
    ResumeDetailView,
    ResumeDownloadView,
    ResumeListView,
    MasterResumeView,
    SaveTailoredResumeView,
    SetMasterResumeView,
    TailorResumeView,
)


urlpatterns = [

    path(
        "",
        ResumeListView.as_view(),
        name="resume-list",
    ),

    path(
        "master/",
        MasterResumeView.as_view(),
        name="master-resume",
    ),

    # Declared before "<int:pk>/" so these literal paths are not swallowed by
    # the detail route.
    path(
        "qualities/",
        QualitiesView.as_view(),
        name="resume-qualities",
    ),

    path(
        "tailor/",
        TailorResumeView.as_view(),
        name="resume-tailor",
    ),

    path(
        "tailor/save/",
        SaveTailoredResumeView.as_view(),
        name="resume-tailor-save",
    ),

    path(
        "tailor/status/",
        AIProviderStatusView.as_view(),
        name="resume-tailor-status",
    ),

    path(
        "<int:pk>/",
        ResumeDetailView.as_view(),
        name="resume-detail",
    ),

    path(
        "<int:pk>/set-master/",
        SetMasterResumeView.as_view(),
        name="resume-set-master",
    ),

    path(
        "<int:pk>/download/<str:fmt>/",
        ResumeDownloadView.as_view(),
        name="resume-download",
    ),

]
