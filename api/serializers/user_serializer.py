from django.contrib.auth.models import User
from rest_framework import serializers


class UserProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "role",
            "avatar",
            "last_login",
            "is_superuser",
        ]
        read_only_fields = ["id", "username", "role", "avatar", "last_login", "is_superuser"]

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip() or obj.username

    def get_role(self, obj):
        if obj.is_superuser:
            return "Administrator"
        groups = obj.groups.all()
        if groups.exists():
            return groups[0].name
        return "Staff"

    def get_avatar(self, obj):
        if hasattr(obj, "profile") and obj.profile.avatar:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.profile.avatar.url)
            return obj.profile.avatar.url
        return None


class AvatarUploadSerializer(serializers.Serializer):
    avatar = serializers.FileField(required=True)


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is not correct")
        return value

    def validate_new_password(self, value):
        # We could add more validation here if needed
        if len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long")
        return value
