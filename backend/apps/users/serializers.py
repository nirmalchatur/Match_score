from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers

from .models import UserProfile

User = get_user_model()


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = [
            "headline",
            "discipline",
            "target_locations",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class UserSerializer(serializers.ModelSerializer):
    """Public representation of the signed-in account."""

    profile = serializers.SerializerMethodField()
    has_master_resume = serializers.SerializerMethodField()
    job_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "date_joined",
            "profile",
            "has_master_resume",
            "job_count",
        ]
        read_only_fields = ["id", "email", "date_joined"]

    def get_profile(self, obj):
        # Not every account has a profile row (admin-created users), so this
        # must not assume the reverse one-to-one exists.
        try:
            profile = obj.profile
        except ObjectDoesNotExist:
            return None
        return UserProfileSerializer(profile).data

    def get_has_master_resume(self, obj):
        # Uses the reverse relation so the check stays user-scoped.
        resumes = getattr(obj, "resumes", None)
        if resumes is None:
            return False
        return resumes.filter(is_master=True).exists()

    def get_job_count(self, obj):
        jobs = getattr(obj, "jobs", None)
        return jobs.count() if jobs is not None else 0


class RegisterSerializer(serializers.Serializer):
    """Creates a TailorUp account and its profile in one step."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    full_name = serializers.CharField(required=False, allow_blank=True, max_length=150)

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return email

    def validate_password(self, value):
        # Reuse Django's configured AUTH_PASSWORD_VALIDATORS.
        validate_password(value)
        return value

    def create(self, validated_data):
        email = validated_data["email"]
        full_name = validated_data.get("full_name", "").strip()

        first_name, _, last_name = full_name.partition(" ")

        # username mirrors the email so the built-in User model stays usable.
        user = User.objects.create_user(
            username=email,
            email=email,
            password=validated_data["password"],
            first_name=first_name,
            last_name=last_name,
        )

        UserProfile.objects.create(user=user)

        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class ProviderCredentialSerializer(serializers.Serializer):
    """Accepts a user's own API key. The key is write-only, by construction.

    Declaring ``api_key`` write-only means it can never be echoed back by the
    default ``to_representation``, so it is impossible to leak a key through
    this serializer even if someone serialises the object by mistake later.
    The read side is built by hand in :meth:`ProviderCredential.public_dict`,
    which has no key field at all.
    """

    #: Restricted to a known set so this endpoint cannot be used to stash
    #: arbitrary blobs against a user.
    provider = serializers.ChoiceField(
        choices=["gemini"],
        default="gemini",
    )

    api_key = serializers.CharField(
        write_only=True,
        # Deliberately NOT trim_whitespace=True: that would strip a trailing
        # newline before validate_api_key ever sees it, hiding a truncated
        # paste. The raw value is inspected instead.
        trim_whitespace=False,
        min_length=8,
        max_length=200,
        error_messages={
            "min_length": "That key looks too short to be a real API key.",
            "max_length": "That key is longer than any known provider key.",
        },
    )

    def validate_api_key(self, value):
        # The whitespace check runs on the raw value, before trim_whitespace
        # has silently stripped a trailing newline. A pasted key often arrives
        # with one, and quietly trimming it hides a truncated paste -- better to
        # say so and let the user re-copy.
        if any(ch.isspace() for ch in value):
            raise serializers.ValidationError(
                "An API key cannot contain spaces. Check for a stray newline "
                "or a missing character."
            )

        key = value.strip()
        if not key:
            raise serializers.ValidationError("Enter your API key.")
        # A shape check, not a validity check. The goal is to catch a pasted
        # URL or a truncated string early and give a clear message; whether
        # the key actually works is only knowable by calling the provider, and
        # that happens on first use.
        if key.lower().startswith(("http://", "https://")):
            raise serializers.ValidationError(
                "That is a URL, not an API key. Copy the key itself from "
                "Google AI Studio."
            )
        return key

