from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class CustomTokenObtainSerializer(TokenObtainPairSerializer):
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
        if hasattr(user, "profile") and user.profile.avatar:
            token["avatar"] = user.profile.avatar.url
        else:
            token["avatar"] = None
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        return {"token": data.get("access")}
