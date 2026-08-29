from django.contrib import admin
from django.urls import path, include


urlpatterns = [

    path(
        "admin/",
        admin.site.urls,
    ),

    path(
        "api/jobs/",
        include("apps.jobs.urls"),
    ),

    path(
        "api/resumes/",
        include("apps.resumes.urls"),
    ),

]