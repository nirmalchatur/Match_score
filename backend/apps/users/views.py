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

from .models import UserProfile
from .serializers import (
    LoginSerializer,
    RegisterSerializer,
    UserProfileSerializer,
    UserSerializer,
)


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
    """POST /api/auth/logout/ — end the session."""

    permission_classes = [AllowAny]

    def post(self, request):
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


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
