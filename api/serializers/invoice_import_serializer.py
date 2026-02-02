"""
Invoice Import Serializers
Serializers for invoice import API endpoints.
"""

from rest_framework import serializers


class LLMModelSerializer(serializers.Serializer):
    """Serializer for a single LLM model option."""

    id = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()


class LLMProviderSerializer(serializers.Serializer):
    """Serializer for an LLM provider with its models."""

    name = serializers.CharField()
    models = LLMModelSerializer(many=True)


class InvoiceImportConfigSerializer(serializers.Serializer):
    """Serializer for import configuration including LLM providers."""

    providers = serializers.DictField(child=LLMProviderSerializer())
    currentProvider = serializers.CharField()
    currentModel = serializers.CharField()
    maxWorkers = serializers.IntegerField()
    supportedFormats = serializers.ListField(child=serializers.CharField())


class ImportedCustomerSerializer(serializers.Serializer):
    """Serializer for the customer extracted from an imported invoice."""

    id = serializers.IntegerField()
    title = serializers.CharField(allow_blank=True, allow_null=True)
    name = serializers.CharField()
    email = serializers.CharField(allow_blank=True, allow_null=True)
    phone = serializers.CharField(allow_blank=True, allow_null=True)
    address = serializers.CharField(allow_blank=True, allow_null=True)
    company = serializers.CharField(allow_blank=True, allow_null=True)
    npwp = serializers.CharField(allow_blank=True, allow_null=True)


class ImportedInvoiceSerializer(serializers.Serializer):
    """Serializer for the invoice created from import."""

    id = serializers.IntegerField()
    invoiceNo = serializers.CharField(source="invoice_no")
    customerName = serializers.CharField(source="customer_name")
    totalAmount = serializers.CharField(source="total_amount")
    invoiceDate = serializers.CharField(source="invoice_date")
    status = serializers.CharField()
    url = serializers.CharField()


class InvoiceSingleImportResultSerializer(serializers.Serializer):
    """Serializer for single invoice import result."""

    success = serializers.BooleanField()
    status = serializers.CharField()  # 'imported', 'duplicate', 'error'
    message = serializers.CharField()
    filename = serializers.CharField()
    invoice = ImportedInvoiceSerializer(required=False, allow_null=True)
    customer = ImportedCustomerSerializer(required=False, allow_null=True)
    errors = serializers.ListField(child=serializers.CharField(), required=False)


class InvoiceBatchImportStartSerializer(serializers.Serializer):
    """Serializer for batch import job initiation response."""

    jobId = serializers.UUIDField(source="job_id")
    status = serializers.CharField()
    progress = serializers.IntegerField()
    totalFiles = serializers.IntegerField(source="total_files")
    streamUrl = serializers.CharField(source="stream_url")
    statusUrl = serializers.CharField(source="status_url")


class InvoiceImportJobStatusSerializer(serializers.Serializer):
    """Serializer for import job status."""

    jobId = serializers.UUIDField(source="job_id")
    status = serializers.CharField()
    progress = serializers.IntegerField()
    totalFiles = serializers.IntegerField(source="total_files")
    processedFiles = serializers.IntegerField(source="processed_files")
    importedCount = serializers.IntegerField(source="imported_count")
    duplicateCount = serializers.IntegerField(source="duplicate_count")
    errorCount = serializers.IntegerField(source="error_count")
