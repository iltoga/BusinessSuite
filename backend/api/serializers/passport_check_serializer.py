from rest_framework import serializers


class PassportCheckSerializer(serializers.Serializer):
    file = serializers.FileField(required=True, help_text="Passport image file")
    method = serializers.ChoiceField(choices=["ai", "hybrid"], default="hybrid", help_text="Verification method")
