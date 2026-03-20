import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.db.utils import DatabaseError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from core.models.user_profile import UserProfile

logger = logging.getLogger(__name__)
User = get_user_model()


def _serialize_user(user) -> dict[str, object]:
    groups = list(user.groups.values_list("name", flat=True))
    full_name = f"{user.first_name} {user.last_name}".strip() or user.username
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": full_name,
        "avatar": CustomTokenObtainSerializer._resolve_avatar_url(user.id),
        "roles": groups,
        "groups": groups,
        "is_superuser": user.is_superuser,
        "is_staff": user.is_staff,
    }


class CustomTokenObtainSerializer(TokenObtainPairSerializer):
    @staticmethod
    def _resolve_avatar_url(user_id):
        try:
            avatar_path = UserProfile.objects.filter(user_id=user_id).values_list("avatar", flat=True).first()
        except DatabaseError as exc:
            logger.warning("Unable to resolve avatar for user_id=%s: %s", user_id, exc)
            return None

        if not avatar_path:
            return None

        try:
            return default_storage.url(avatar_path)
        except Exception as exc:
            logger.warning("Unable to build avatar URL for user_id=%s: %s", user_id, exc)
            return None

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        groups = list(user.groups.values_list("name", flat=True))
        token["email"] = user.email
        token["fullName"] = f"{user.first_name} {user.last_name}".strip() or user.username
        token["roles"] = groups
        token["groups"] = groups
        token["is_superuser"] = user.is_superuser
        token["is_staff"] = user.is_staff
        token["avatar"] = cls._resolve_avatar_url(user.id)
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        user = getattr(self, "user", None)
        if user is None:
            raise serializers.ValidationError("Authenticated user could not be resolved.")
        return {
            "access_token": data.get("access"),
            "refresh_token": data.get("refresh"),
            "user": _serialize_user(user),
        }


class CustomTokenRefreshSerializer(TokenRefreshSerializer):
    refresh = serializers.CharField(required=False, allow_blank=False)

    def validate(self, attrs):
        request = self.context.get("request")
        cookie_name = getattr(settings, "JWT_REFRESH_COOKIE_NAME", "bs_refresh_token")
        refresh = attrs.get("refresh")
        if not refresh and request is not None:
            refresh = request.COOKIES.get(cookie_name)
        if not refresh:
            raise serializers.ValidationError({"refresh_token": "Refresh token is required."})

        attrs["refresh"] = refresh
        data = super().validate(attrs)

        try:
            refresh_token = RefreshToken(refresh)
            user_id = refresh_token.get("user_id")
            user = User.objects.get(pk=user_id) if user_id is not None else None
        except Exception:
            user = None

        return {
            "access_token": data.get("access"),
            "refresh_token": data.get("refresh", refresh),
            "user": _serialize_user(user) if user is not None else None,
        }
