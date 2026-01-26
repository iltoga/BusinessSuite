from .country_code_serializer import CountryCodeSerializer
from .customer_serializer import CustomerSerializer
from .doc_application_serializer import (
    DocApplicationDetailSerializer,
    DocApplicationSerializer,
    DocApplicationSerializerWithRelations,
)
from .doc_workflow_serializer import DocWorkflowSerializer, TaskSerializer
from .document_serializer import DocumentSerializer
from .document_type_serializer import DocumentTypeSerializer
from .product_serializer import ProductCreateUpdateSerializer, ProductDetailSerializer, ProductSerializer
from .quick_create_serializer import (
    CustomerApplicationQuickCreateSerializer,
    CustomerQuickCreateSerializer,
    ProductQuickCreateSerializer,
)
