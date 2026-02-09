from rest_framework import serializers


class DashboardStatsSerializer(serializers.Serializer):
    customers = serializers.IntegerField()
    applications = serializers.IntegerField()
    invoices = serializers.IntegerField()
