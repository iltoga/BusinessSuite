"""
FILE_ROLE: Serializer and payload-shaping helpers for the API app.

KEY_COMPONENTS:
- PaymentSerializer: Serializer class.
- InvoiceApplicationSummarySerializer: Serializer class.
- InvoiceApplicationDetailSerializer: Serializer class.
- InvoiceListSerializer: Serializer class.
- InvoiceDetailSerializer: Serializer class.
- InvoiceApplicationWriteSerializer: Serializer class.
- InvoiceCreateUpdateSerializer: Serializer class.

INTERACTIONS:
- Depends on: nearby Django models, services, serializers, and the app packages imported by this module.

AI_GUIDELINES:
- Keep the module focused on serializer validation and representation only.
- Preserve the existing API contract because client code and views depend on these field names.
"""

from api.serializers.customer_serializer import CustomerSerializer
from api.serializers.doc_application_serializer import DocApplicationInvoiceSerializer
from api.serializers.product_serializer import ProductSerializer
from customer_applications.models import DocApplication
from invoices.models.invoice import Invoice, InvoiceApplication
from payments.models import Payment
from products.models import Product
from rest_framework import serializers


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
    product = ProductSerializer(read_only=True)
    customer_application = DocApplicationInvoiceSerializer(read_only=True, allow_null=True)
    paid_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    due_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = InvoiceApplication
        fields = [
            "id",
            "product",
            "customer_application",
            "amount",
            "status",
            "paid_amount",
            "due_amount",
        ]


class InvoiceApplicationDetailSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    customer_application = DocApplicationInvoiceSerializer(read_only=True, allow_null=True)
    payments = PaymentSerializer(many=True, read_only=True)
    paid_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    due_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = InvoiceApplication
        fields = [
            "id",
            "product",
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
    created_by = serializers.SlugRelatedField(read_only=True, slug_field="username")
    updated_by = serializers.SlugRelatedField(read_only=True, slug_field="username")

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
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "invoice_applications",
        ]

    def get_invoice_no_display(self, instance) -> str:
        return instance.invoice_no_display


class InvoiceDetailSerializer(serializers.ModelSerializer):
    customer = CustomerSerializer(read_only=True)
    invoice_no_display = serializers.SerializerMethodField()
    total_paid_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total_due_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    invoice_applications = InvoiceApplicationDetailSerializer(many=True, read_only=True)
    created_by = serializers.SlugRelatedField(read_only=True, slug_field="username")
    updated_by = serializers.SlugRelatedField(read_only=True, slug_field="username")

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
            "created_by",
            "updated_by",
            "invoice_applications",
        ]

    def get_invoice_no_display(self, instance) -> str:
        return instance.invoice_no_display


class InvoiceApplicationWriteSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all(), required=False, allow_null=True)
    customer_application = serializers.PrimaryKeyRelatedField(
        queryset=DocApplication.objects.all(),
        required=False,
        allow_null=True,
    )
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)

    def validate(self, attrs):
        product = attrs.get("product")
        customer_application = attrs.get("customer_application")
        if not product and not customer_application:
            raise serializers.ValidationError("Each invoice line must include a product or customer application.")
        if customer_application and product and customer_application.product_id != product.id:
            raise serializers.ValidationError("Invoice line product must match the customer application product.")
        return attrs


class InvoiceCreateUpdateSerializer(serializers.ModelSerializer):
    invoice_no = serializers.IntegerField(required=False, allow_null=True)
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
        if not value:
            raise serializers.ValidationError("An invoice must have at least one line item.")
        customer_ids = [item.get("customer_application") for item in value if item.get("customer_application")]
        if len(customer_ids) != len(set(customer_ids)):
            raise serializers.ValidationError("Each customer application can only appear once in an invoice.")
        return value
