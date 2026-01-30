from django.conf import settings
from django.contrib.auth.models import Group, User
from rest_framework_simplejwt.authentication import JWTAuthentication


def _get_mock_user_settings():
    return {
        "username": getattr(settings, "MOCK_AUTH_USERNAME", "mockuser"),
        "email": getattr(settings, "MOCK_AUTH_EMAIL", "mock@example.com"),
        "is_staff": getattr(settings, "MOCK_AUTH_IS_STAFF", True),
        "is_superuser": getattr(settings, "MOCK_AUTH_IS_SUPERUSER", True),
        "groups": getattr(settings, "MOCK_AUTH_GROUPS", []),
    }


def ensure_mock_user() -> User:
    config = _get_mock_user_settings()
    user, _ = User.objects.get_or_create(
        username=config["username"],
        defaults={
            "is_staff": config["is_staff"],
            "is_superuser": config["is_superuser"],
            "email": config["email"],
        },
    )

    update_fields = []
    if user.email != config["email"]:
        user.email = config["email"]
        update_fields.append("email")
    if user.is_staff != config["is_staff"]:
        user.is_staff = config["is_staff"]
        update_fields.append("is_staff")
    if user.is_superuser != config["is_superuser"]:
        user.is_superuser = config["is_superuser"]
        update_fields.append("is_superuser")

    if update_fields:
        user.save(update_fields=update_fields)

    groups = config.get("groups")
    if groups is not None:
        group_objects = [Group.objects.get_or_create(name=group_name)[0] for group_name in groups]
        user.groups.set(group_objects)

    return user


class JwtOrMockAuthentication(JWTAuthentication):
    def authenticate(self, request):
        if getattr(settings, "MOCK_AUTH_ENABLED", False):
            header = self.get_header(request)
            if header is not None:
                raw_token = self.get_raw_token(header)
                if raw_token is not None:
                    token_value = raw_token.decode() if isinstance(raw_token, bytes) else str(raw_token)
                    if token_value == "mock-token":
                        user = ensure_mock_user()
                        return (user, None)

        return super().authenticate(request)
