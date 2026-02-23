import logging

from django.core.files.storage import default_storage
from django.db.utils import DatabaseError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from core.models.user_profile import UserProfile

logger = logging.getLogger(__name__)


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
        return {"token": data.get("access")}
