from rest_framework import serializers


class SuratPermohonanRequestSerializer(serializers.Serializer):
    customer_id = serializers.IntegerField(required=True)
    doc_date = serializers.CharField(required=False, allow_blank=True)
    visa_type = serializers.CharField(required=False, allow_blank=True)
    name = serializers.CharField(required=False, allow_blank=True)
    gender = serializers.CharField(required=False, allow_blank=True)
    country = serializers.CharField(required=False, allow_blank=True)
    birth_place = serializers.CharField(required=False, allow_blank=True)
    birthdate = serializers.CharField(required=False, allow_blank=True)
    passport_no = serializers.CharField(required=False, allow_blank=True)
    passport_exp_date = serializers.CharField(required=False, allow_blank=True)
    address_bali = serializers.CharField(required=False, allow_blank=True)


class SuratPermohonanCustomerDataSerializer(serializers.Serializer):
    name = serializers.CharField()
    gender = serializers.CharField(allow_blank=True, required=False)
    country = serializers.CharField(allow_blank=True, required=False, allow_null=True)
    birth_place = serializers.CharField(allow_blank=True, required=False)
    birthdate = serializers.CharField(allow_blank=True, required=False, allow_null=True)
    passport_no = serializers.CharField(allow_blank=True, required=False)
    passport_exp_date = serializers.CharField(allow_blank=True, required=False, allow_null=True)
    address_bali = serializers.CharField(allow_blank=True, required=False)
