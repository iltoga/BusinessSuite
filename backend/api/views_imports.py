import json
import logging
import mimetypes
import os
import time
import uuid
from datetime import datetime, timedelta
from io import BytesIO
from typing import Any, Generator, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from api.permissions import (
    STAFF_OR_ADMIN_PERMISSION_REQUIRED_ERROR,
    IsAdminOrManagerGroup,
    IsStaffOrAdminGroup,
    is_staff_or_admin_group,
    is_superuser,
)
from api.serializers import (
    AdminPushNotificationSendSerializer,
    AdminWhatsappTestSendSerializer,
    AiModelSerializer,
    AsyncJobSerializer,
    AvatarUploadSerializer,
    CalendarReminderBulkCreateSerializer,
    CalendarReminderCreateSerializer,
    CalendarReminderInboxMarkReadSerializer,
    CalendarReminderInboxSnoozeSerializer,
    CalendarReminderSerializer,
    ChangePasswordSerializer,
    CountryCodeSerializer,
    CustomerApplicationHistorySerializer,
    CustomerApplicationQuickCreateSerializer,
    CustomerQuickCreateSerializer,
    CustomerSerializer,
    CustomerUninvoicedApplicationSerializer,
    DashboardStatsSerializer,
    DocApplicationDetailSerializer,
    DocApplicationInvoiceSerializer,
    DocApplicationSerializerWithRelations,
    DocumentMergeSerializer,
    DocumentSerializer,
    DocumentTypeSerializer,
    DocWorkflowSerializer,
    HolidaySerializer,
    InvoiceCreateUpdateSerializer,
    InvoiceDetailSerializer,
    InvoiceListSerializer,
    PaymentSerializer,
    ProductCategoryFilterOptionSerializer,
    ProductCreateUpdateSerializer,
    ProductDetailSerializer,
    ProductImportStartResponseSerializer,
    ProductImportStartSerializer,
    ProductPriceListPrintStartResponseSerializer,
    ProductPriceListPrintStartSerializer,
    ProductQuickCreateSerializer,
    ProductSerializer,
    PushNotificationTestSerializer,
    SuratPermohonanCustomerDataSerializer,
    SuratPermohonanRequestSerializer,
    UserProfileSerializer,
    UserSettingsSerializer,
    WebPushSubscriptionDeleteSerializer,
    WebPushSubscriptionSerializer,
    WebPushSubscriptionUpsertSerializer,
    WorkflowNotificationSerializer,
    ordered_document_types,
)
from api.serializers.auth_serializer import CustomTokenObtainSerializer, CustomTokenRefreshSerializer
from api.serializers.passport_check_serializer import PassportCheckSerializer
from api.utils.redis_sse import iter_replay_and_live_events
from api.utils.sse_auth import sse_token_auth_required
from api.utils.contracts import build_error_payload, build_success_payload
from business_suite.authentication import JwtOrMockAuthentication
from core.models import (
    AiModel,
    AsyncJob,
    CalendarReminder,
    CountryCode,
    DocumentOCRJob,
    Holiday,
    OCRJob,
    UserProfile,
    UserSettings,
    WebPushSubscription,
)
from core.services.ai_runtime_settings_service import AIRuntimeSettingsService
from core.services.calendar_reminder_service import CalendarReminderService
from core.services.document_merger import DocumentMerger, DocumentMergerError
from core.services.ocr_preview_storage import get_ocr_preview_url
from core.services.push_notifications import FcmConfigurationError, PushNotificationService
from core.services.quick_create import create_quick_customer, create_quick_customer_application, create_quick_product
from core.services.redis_streams import format_sse_event, resolve_last_event_id, stream_job_key, stream_user_key
from core.tasks.cron_jobs import enqueue_clear_cache_now, enqueue_full_backup_now
from core.tasks.document_ocr import run_document_ocr_job
from core.tasks.document_validation import run_document_validation
from core.tasks.ocr import run_ocr_job
from core.utils.dateutils import calculate_due_date
from core.utils.pdf_converter import PDFConverter, PDFConverterError
from customer_applications.models import DocApplication, Document, DocWorkflow, WorkflowNotification
from customer_applications.services.workflow_notification_stream import RECENT_WORKFLOW_NOTIFICATION_WINDOW_HOURS
from customers.models import Customer
from customers.tasks import check_passport_uploadability_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth import logout as django_logout
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import (
    Case,
    Count,
    DecimalField,
    F,
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce, Lower, NullIf
from django.http import FileResponse, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.text import get_valid_filename, slugify
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from invoices.models import InvoiceDownloadJob
from invoices.models.invoice import Invoice, InvoiceApplication
from invoices.services.InvoiceService import InvoiceService
from invoices.tasks.download_jobs import run_invoice_download_job
from letters.services.LetterService import LetterService
from payments.models import Payment
from products.models import Product, ProductCategory
from products.models.document_type import DocumentType
from products.models.task import Task
from rest_framework import filters, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action, api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views_shared import (
    ASYNC_JOB_INFLIGHT_STATUSES,
    QUEUE_JOB_INFLIGHT_STATUSES,
    ApiErrorHandlingMixin,
    ComputePlaceholderSerializer,
    CronScopedRateThrottle,
    DocumentOCRPlaceholderSerializer,
    OCRPlaceholderSerializer,
    QuickCreateScopedRateThrottle,
)
from .views_shared import ResilientAnonRateThrottle as AnonRateThrottle
from .views_shared import ResilientScopedRateThrottle as ScopedRateThrottle
from .views_shared import ResilientUserRateThrottle as UserRateThrottle
from .views_shared import (
    StandardResultsSetPagination,
    _get_enqueue_guard_token,
    _latest_inflight_job,
    _observe_async_guard_event,
    parse_bool,
    prepare_async_enqueue,
    release_enqueue_guard,
    restrict_to_owner_unless_privileged,
)

logger = logging.getLogger(__name__)
