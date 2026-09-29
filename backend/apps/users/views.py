"""
Session-based authentication for the TailorUp SPA.

We use Django's built-in session auth rather than tokens so the browser
holds an HttpOnly session cookie and no secret is ever exposed to
JavaScript. `ensure_csrf_cookie` on the "me" endpoint guarantees the SPA
can always obtain a CSRF token for mutating requests.

Cross-origin note
-----------------
The SPA (Vercel) and this API (Render) are different origins, so the
classic "read the csrftoken cookie with document.cookie" trick cannot work:
a page can only read cookies belonging to its own host, and this API's
cookies are set on the Render domain. `document.cookie` in the browser
therefore returns nothing, and the SPA has no way to discover the token from
the cookie it is *sent*.

`CsrfTokenView` exists for that. It returns the token in the response body so
the client can hold it in memory and echo it in the `X-CSRFToken` header,
which is the arrangement DRF's SessionAuthentication expects.
"""

from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ProviderCredential, UserProfile
from .serializers import (
    LoginSerializer,
    ProviderCredentialSerializer,
    RegisterSerializer,
    UserProfileSerializer,
    UserSerializer,
)

from apps.common.throttling import SignupRateThrottle, StrictAnonRateThrottle


class CsrfTokenView(APIView):
    """GET /api/auth/csrf/ — hand the SPA a CSRF token it can actually read.

    The `ensure_csrf_cookie` decorator is not optional: DRF's
    SessionAuthentication performs the double-submit comparison, so the token
    has to be in the cookie *as well* as the header. Returning it in the body
    is what makes it reachable from a page on another origin.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        return Response({"csrf_token": get_token(request)})


class RegisterView(APIView):
    throttle_classes = [SignupRateThrottle]
    """POST /api/auth/register/ — create an account and sign in."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.save()

        # Log the new account straight in so onboarding can continue.
        login(request._request, user)

        return Response(
            {"user": UserSerializer(user).data},
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    throttle_classes = [StrictAnonRateThrottle]
    """POST /api/auth/login/ — start a session."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].strip().lower()
        password = serializer.validated_data["password"]

        user = authenticate(
            request._request,
            username=email,
            password=password,
        )

        if user is None:
            return Response(
                {"error": "Incorrect email or password."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user.is_active:
            return Response(
                {"error": "This account has been deactivated."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        login(request._request, user)

        return Response(
            {"user": UserSerializer(user).data},
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    """POST /api/auth/logout/ — end the session and drop the stored key.

    The credential is deleted here, not just forgotten. Signing out on a shared
    or borrowed machine should leave nothing behind, and an API key sitting in
    the database is worth as much as a password. The scope is deliberately
    exact: only *this* user's rows, only the signed-in account, and only when
    the request actually carried a session.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        # Resolved before logout() flushes the session, otherwise request.user
        # is anonymous and the delete below would match nothing.
        user = request.user if getattr(request.user, "is_authenticated", False) else None

        if user is not None:
            # Scoped to this user's rows only. Deliberately not a table-wide
            # clear, and it does not touch any other account's key.
            ProviderCredential.objects.filter(user=user).delete()

        logout(request._request)

        # Still 204, unchanged: the credential deletion is a side effect of
        # signing out, not something the client asked to be told about, and
        # the Postman collection asserts this status.
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProviderCredentialView(APIView):
    """GET/POST/DELETE the current user's own AI provider key.

    The contract that matters here: **no endpoint in this project ever returns
    a stored key.** The key goes in on POST and the server keeps it; GET tells
    the UI only whether one exists, plus a 4+4 character hint so a user with
    two keys can tell them apart. There is no GET-one-key route by design --
    a reveal would put the value in a browser cache and every proxy log
    between the server and the page.
    """

    permission_classes = [IsAuthenticated]

    #: Matches ProviderCredentialSerializer.provider. Kept adjacent so adding a
    #: provider in one place is visible as a failure in the other.
    PROVIDERS = ("gemini", "groq")

    def _lookup(self, request, provider):
        """The caller's own row, or None.

        Keyed on request.user rather than any id in the request body, so there
        is no user-controlled path to another account's credential.
        """
        return ProviderCredential.objects.filter(
            user=request.user,
            provider=provider,
        ).first()

    def _status_payload(self, request, provider):
        credential = self._lookup(request, provider)
        if credential is None:
            return {"provider": provider, "configured": False}
        return {
            "provider": credential.provider,
            "configured": True,
            "key_hint": credential.key_hint,
            "updated_at": credential.updated_at,
        }

    def get(self, request):
        """Report configuration status. Never the key itself."""
        provider = request.query_params.get("provider", "gemini")
        if provider not in self.PROVIDERS:
            return Response(
                {"error": f"Unknown provider '{provider}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(self._status_payload(request, provider))

    def post(self, request):
        """Save or replace the caller's key for a provider."""
        serializer = ProviderCredentialSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        provider = serializer.validated_data["provider"]
        plaintext = serializer.validated_data["api_key"]

        credential, _ = ProviderCredential.objects.get_or_create(
            user=request.user,
            provider=provider,
        )
        # get_or_create needs a non-null encrypted_key to insert; set_key
        # overwrites it immediately either way.
        if credential.pk and not credential.encrypted_key:
            credential.encrypted_key = ""

        credential.set_key(plaintext)
        credential.save()

        # The plaintext is now out of scope. Nothing above this line returns or
        # logs it.
        return Response(
            self._status_payload(request, provider),
            status=status.HTTP_201_CREATED,
        )

    def delete(self, request):
        """Forget the caller's key for a provider. Idempotent."""
        provider = request.query_params.get("provider", "gemini")
        if provider not in self.PROVIDERS:
            return Response(
                {"error": f"Unknown provider '{provider}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Delete via the queryset rather than the model instance: _lookup
        # returns None when nothing is stored, and None.delete() is an
        # AttributeError rather than the idempotent no-op a caller expects.
        ProviderCredential.objects.filter(
            user=request.user,
            provider=provider,
        ).delete()

        return Response(
            {"provider": provider, "configured": False},
            status=status.HTTP_200_OK,
        )


class MeView(APIView):
    """
    GET /api/auth/me/ — current account, or an unauthenticated marker.

    Also seeds the CSRF cookie the SPA needs for later mutations. The
    decorator is applied to `get` rather than the class, because wrapping
    the class would turn it into a plain function and break `.as_view()`.
    """

    permission_classes = [AllowAny]

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        if not request.user.is_authenticated:
            return Response(
                {"user": None, "authenticated": False},
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "user": UserSerializer(request.user).data,
                "authenticated": True,
            },
            status=status.HTTP_200_OK,
        )


class ProfileView(APIView):
    """GET/PATCH /api/auth/profile/ — workspace settings."""

    permission_classes = [IsAuthenticated]

    def _profile(self, user):
        # Query by field rather than the reverse accessor: accounts created
        # outside the signup endpoint (admin, createsuperuser) have no
        # profile row, and touching user.profile would raise.
        profile, _ = UserProfile.objects.get_or_create(user=user)
        return profile

    def get(self, request):
        return Response(
            UserProfileSerializer(self._profile(request.user)).data,
            status=status.HTTP_200_OK,
        )

    def patch(self, request):
        profile = self._profile(request.user)
        serializer = UserProfileSerializer(
            profile,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            UserProfileSerializer(profile).data,
            status=status.HTTP_200_OK,
        )
