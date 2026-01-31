from .country_code_serializer import CountryCodeSerializer
from .customer_serializer import CustomerSerializer
from .doc_application_serializer import (
    DocApplicationCreateUpdateSerializer,
    DocApplicationDetailSerializer,
    DocApplicationInvoiceSerializer,
    DocApplicationSerializer,
    DocApplicationSerializerWithRelations,
)
from .doc_workflow_serializer import DocWorkflowSerializer, TaskSerializer
from .document_serializer import DocumentMergeSerializer, DocumentSerializer
from .document_type_serializer import DocumentTypeSerializer
from .invoice_serializer import (
    InvoiceCreateUpdateSerializer,
    InvoiceDetailSerializer,
    InvoiceListSerializer,
    PaymentSerializer,
)
from .letters_serializer import SuratPermohonanCustomerDataSerializer, SuratPermohonanRequestSerializer
from .product_serializer import ProductCreateUpdateSerializer, ProductDetailSerializer, ProductSerializer
from .quick_create_serializer import (
    CustomerApplicationQuickCreateSerializer,
    CustomerQuickCreateSerializer,
    ProductQuickCreateSerializer,
)
