from rest_framework import serializers

from core.models import WebPushSubscription


class WebPushSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebPushSubscription
        fields = [
            "id",
            "device_label",
            "is_active",
            "last_error",
            "last_seen_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class WebPushSubscriptionUpsertSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=512)
    device_label = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    user_agent = serializers.CharField(required=False, allow_blank=True, default="")


class WebPushSubscriptionDeleteSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=512)


class PushNotificationTestSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=120, required=False, default="Revis Bali CRM Notification")
    body = serializers.CharField(max_length=500, required=False, default="Push notification test completed.")
    data = serializers.DictField(required=False, default=dict)
    link = serializers.CharField(required=False, allow_blank=True, default="")


class AdminPushNotificationSendSerializer(PushNotificationTestSerializer):
    user_id = serializers.IntegerField(required=True, min_value=1)


class AdminWhatsappTestSendSerializer(serializers.Serializer):
    to = serializers.CharField(required=False, allow_blank=True, default="")
    subject = serializers.CharField(max_length=120, required=False, default="Revis Bali CRM WhatsApp Test")
    body = serializers.CharField(
        max_length=1000,
        required=False,
        default="WhatsApp test message from Revis Bali CRM.",
    )
