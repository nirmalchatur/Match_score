from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include


urlpatterns = [

    path(
        "admin/",
        admin.site.urls,
    ),

    path(
        "api/auth/",
        include("apps.users.urls"),
    ),

    path(
        "api/applications/",
        include("apps.applications.urls"),
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


# Django does not serve media on its own. In development this is handled
# automatically; on Render/Gunicorn we must add the route explicitly, since
# there is no separate web server in front.
urlpatterns += static(
    settings.MEDIA_URL,
    document_root=settings.MEDIA_ROOT,
)
