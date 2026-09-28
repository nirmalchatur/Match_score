from django.urls import path

from .views import (
    CsrfTokenView,
    LoginView,
    LogoutView,
    MeView,
    ProfileView,
    ProviderCredentialView,
    RegisterView,
)


urlpatterns = [
    path(
        "csrf/",
        CsrfTokenView.as_view(),
        name="auth-csrf",
    ),
    path(
        "register/",
        RegisterView.as_view(),
        name="auth-register",
    ),
    path(
        "login/",
        LoginView.as_view(),
        name="auth-login",
    ),
    path(
        "logout/",
        LogoutView.as_view(),
        name="auth-logout",
    ),
    path(
        "me/",
        MeView.as_view(),
        name="auth-me",
    ),
    path(
        "profile/",
        ProfileView.as_view(),
        name="auth-profile",
    ),
    # The user's own Google AI Studio key. Status/save/remove only; the key
    # itself is never returned by any method.
    path(
        "ai-key/",
        ProviderCredentialView.as_view(),
        name="auth-ai-key",
    ),
]
