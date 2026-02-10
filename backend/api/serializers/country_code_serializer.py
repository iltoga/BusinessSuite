from rest_framework import serializers

from core.models import CountryCode


class CountryCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CountryCode
        fields = ["country", "country_idn", "alpha2_code", "alpha3_code", "numeric_code"]
