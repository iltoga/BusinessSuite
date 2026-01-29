from rest_framework import serializers

from api.serializers.customer_serializer import CustomerSerializer
from api.serializers.doc_application_serializer import DocApplicationInvoiceSerializer
from invoices.models.invoice import Invoice, InvoiceApplication
from payments.models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "id",
            "invoice_application",
            "from_customer",
            "payment_date",
            "payment_type",
            "amount",
            "notes",
            "created_at",
            "created_by",
        ]
        read_only_fields = ["id", "created_at", "created_by"]
        extra_kwargs = {"from_customer": {"required": False}}


class InvoiceApplicationSummarySerializer(serializers.ModelSerializer):
    customer_application = DocApplicationInvoiceSerializer(read_only=True)
    paid_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    due_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = InvoiceApplication
        fields = [
            "id",
            "customer_application",
            "amount",
            "status",
            "paid_amount",
            "due_amount",
        ]


class InvoiceApplicationDetailSerializer(serializers.ModelSerializer):
    customer_application = DocApplicationInvoiceSerializer(read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    paid_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    due_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = InvoiceApplication
        fields = [
            "id",
            "customer_application",
            "amount",
            "status",
            "paid_amount",
            "due_amount",
            "payments",
        ]


class InvoiceListSerializer(serializers.ModelSerializer):
    customer = CustomerSerializer(read_only=True)
    invoice_no_display = serializers.SerializerMethodField()
    total_paid_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total_due_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    invoice_applications = InvoiceApplicationSummarySerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "customer",
            "invoice_no",
            "invoice_no_display",
            "invoice_date",
            "due_date",
            "status",
            "total_amount",
            "total_paid_amount",
            "total_due_amount",
            "is_expired",
            "imported",
            "imported_from_file",
            "invoice_applications",
        ]

    def get_invoice_no_display(self, instance):
        return instance.invoice_no_display


class InvoiceDetailSerializer(serializers.ModelSerializer):
    customer = CustomerSerializer(read_only=True)
    invoice_no_display = serializers.SerializerMethodField()
    total_paid_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total_due_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    invoice_applications = InvoiceApplicationDetailSerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "customer",
            "invoice_no",
            "invoice_no_display",
            "invoice_date",
            "due_date",
            "status",
            "notes",
            "sent",
            "total_amount",
            "total_paid_amount",
            "total_due_amount",
            "is_expired",
            "imported",
            "imported_from_file",
            "mobile_phone",
            "bank_details",
            "created_at",
            "updated_at",
            "invoice_applications",
        ]

    def get_invoice_no_display(self, instance):
        return instance.invoice_no_display


class InvoiceApplicationWriteSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    customer_application = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)


class InvoiceCreateUpdateSerializer(serializers.ModelSerializer):
    invoice_applications = InvoiceApplicationWriteSerializer(many=True)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "customer",
            "invoice_no",
            "invoice_date",
            "due_date",
            "notes",
            "sent",
            "invoice_applications",
        ]
        read_only_fields = ["id"]
        extra_kwargs = {"invoice_no": {"required": False, "allow_null": True}}

    def validate_invoice_applications(self, value):
        customer_ids = [item.get("customer_application") for item in value]
        if len(customer_ids) != len(set(customer_ids)):
            raise serializers.ValidationError("Each customer application can only appear once in an invoice.")
        return value
