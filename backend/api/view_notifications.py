from api.utils.stream_payloads import normalize_async_job_payload, serialize_async_job_payload

from .views_imports import *


@csrf_exempt
@api_view(["GET", "POST"])
@permission_classes([AllowAny])
@authentication_classes([])
def whatsapp_webhook(request):
    """Meta WhatsApp webhook endpoint (verification + delivery statuses + incoming replies)."""
    from notifications.services.providers import process_whatsapp_webhook_payload, verify_meta_webhook_signature

    webhook_logger = logging.getLogger("notifications.whatsapp_webhook")

    if request.method == "GET":
        mode = request.query_params.get("hub.mode")
        challenge = request.query_params.get("hub.challenge", "")
        verify_token = request.query_params.get("hub.verify_token")

        # Meta webhook verification handshake
        if mode == "subscribe":
            expected_token = getattr(settings, "META_TOKEN_CLIENT", "")
            if verify_token and expected_token and verify_token == expected_token:
                return HttpResponse(challenge, status=status.HTTP_200_OK, content_type="text/plain")
            return Response({"error": "Invalid verify token"}, status=status.HTTP_403_FORBIDDEN)

        return Response({"status": "ok"}, status=status.HTTP_200_OK)

    signature_header = request.headers.get("X-Hub-Signature-256")
    signature_valid = verify_meta_webhook_signature(request.body, signature_header)
    enforce_signature = getattr(settings, "META_WEBHOOK_ENFORCE_SIGNATURE", True)
    if not signature_valid:
        if enforce_signature:
            webhook_logger.warning("Rejected WhatsApp webhook due to invalid signature.")
            return Response({"error": "Invalid webhook signature"}, status=status.HTTP_403_FORBIDDEN)
        webhook_logger.warning("Processing WhatsApp webhook with invalid signature (enforcement disabled).")

    data = request.data
    if not isinstance(data, dict):
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            data = request.POST.dict()

    result = process_whatsapp_webhook_payload(data)
    webhook_logger.info(
        "Processed WhatsApp webhook: signature_valid=%s status_updates=%s replies=%s",
        signature_valid,
        result.get("status_updates", 0),
        result.get("replies", 0),
    )
    return Response({"status": "received"}, status=status.HTTP_200_OK)


class WorkflowNotificationViewSet(ApiErrorHandlingMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsStaffOrAdminGroup]
    serializer_class = WorkflowNotificationSerializer
    queryset = WorkflowNotification.objects.select_related("doc_application", "doc_workflow").all()
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["recipient", "subject", "status", "doc_application__id"]
    ordering = ["-id"]

    @action(detail=True, methods=["post"], url_path="resend")
    def resend(self, request, pk=None):
        from customer_applications.tasks import schedule_whatsapp_status_poll
        from notifications.services.providers import NotificationDispatcher, is_queued_provider_result

        notification = self.get_object()
        if notification.status == WorkflowNotification.STATUS_CANCELLED:
            return self.error_response("Cancelled notifications cannot be resent.", status.HTTP_400_BAD_REQUEST)

        attempted_at = timezone.now()
        try:
            result = NotificationDispatcher().send(
                notification.channel,
                notification.recipient,
                notification.subject,
                notification.body,
            )
            notification.provider_message = str(result)
            if is_queued_provider_result(notification.channel, result):
                notification.status = WorkflowNotification.STATUS_PENDING
                notification.sent_at = None
                notification.scheduled_for = attempted_at
                if notification.channel == WorkflowNotification.CHANNEL_WHATSAPP:
                    notification.external_reference = ""
                notification.save(
                    update_fields=[
                        "status",
                        "sent_at",
                        "scheduled_for",
                        "provider_message",
                        "external_reference",
                        "updated_at",
                    ]
                )
            else:
                notification.scheduled_for = attempted_at
                if notification.channel == WorkflowNotification.CHANNEL_WHATSAPP:
                    # Meta accepted response is not delivery confirmation.
                    notification.status = WorkflowNotification.STATUS_PENDING
                    notification.sent_at = None
                    notification.external_reference = str(result)
                else:
                    notification.status = WorkflowNotification.STATUS_SENT
                    notification.sent_at = attempted_at
                notification.save(
                    update_fields=[
                        "status",
                        "sent_at",
                        "scheduled_for",
                        "provider_message",
                        "external_reference",
                        "updated_at",
                    ]
                )
                if notification.channel == WorkflowNotification.CHANNEL_WHATSAPP and notification.external_reference:
                    schedule_whatsapp_status_poll(notification_id=notification.id, delay_seconds=5)
        except Exception as exc:
            notification.status = WorkflowNotification.STATUS_FAILED
            notification.sent_at = None
            notification.scheduled_for = attempted_at
            notification.provider_message = str(exc)
            if notification.channel == WorkflowNotification.CHANNEL_WHATSAPP:
                notification.external_reference = ""
            notification.save(
                update_fields=[
                    "status",
                    "sent_at",
                    "scheduled_for",
                    "provider_message",
                    "external_reference",
                    "updated_at",
                ]
            )
            return self.error_response(str(exc), status.HTTP_400_BAD_REQUEST)

        return Response(self.get_serializer(notification).data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        notification = self.get_object()
        notification.status = WorkflowNotification.STATUS_CANCELLED
        notification.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(notification).data)


class CalendarReminderViewSet(ApiErrorHandlingMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = CalendarReminderSerializer
    queryset = CalendarReminder.objects.select_related("user", "created_by", "calendar_event").all()
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["content", "status", "user__username", "user__first_name", "user__last_name", "user__email"]
    ordering_fields = ["scheduled_for", "created_at", "updated_at", "status_rank"]

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return CalendarReminderCreateSerializer
        if self.action == "bulk_create":
            return CalendarReminderBulkCreateSerializer
        if self.action == "inbox_mark_read":
            return CalendarReminderInboxMarkReadSerializer
        if self.action == "inbox_snooze":
            return CalendarReminderInboxSnoozeSerializer
        return CalendarReminderSerializer

    @staticmethod
    def _safe_positive_int(raw_value, *, default: int, minimum: int = 1, maximum: int | None = None) -> int:
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            value = default

        value = max(value, minimum)
        if maximum is not None:
            value = min(value, maximum)
        return value

    @staticmethod
    def _parse_iso_date(raw_value: str | None):
        if not raw_value:
            return None
        try:
            return datetime.strptime(raw_value.strip(), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .filter(created_by=self.request.user)
            .annotate(
                status_rank=Case(
                    When(status=CalendarReminder.STATUS_PENDING, then=0),
                    When(status=CalendarReminder.STATUS_SENT, then=1),
                    When(status=CalendarReminder.STATUS_FAILED, then=2),
                    default=99,
                    output_field=IntegerField(),
                )
            )
        )

        raw_status = self.request.query_params.get("status")
        if raw_status:
            requested_statuses = [value.strip() for value in raw_status.split(",") if value.strip()]
            allowed_statuses = {choice[0] for choice in CalendarReminder.STATUS_CHOICES}
            statuses = [value for value in requested_statuses if value in allowed_statuses]
            if statuses:
                queryset = queryset.filter(status__in=statuses)

        created_from = self._parse_iso_date(
            self.request.query_params.get("created_from")
            or self.request.query_params.get("createdFrom")
            or self.request.query_params.get("date_from")
            or self.request.query_params.get("dateFrom")
        )
        if created_from:
            queryset = queryset.filter(created_at__date__gte=created_from)

        created_to = self._parse_iso_date(
            self.request.query_params.get("created_to")
            or self.request.query_params.get("createdTo")
            or self.request.query_params.get("date_to")
            or self.request.query_params.get("dateTo")
        )
        if created_to:
            queryset = queryset.filter(created_at__date__lte=created_to)

        if not self.request.query_params.get("ordering"):
            queryset = queryset.order_by("status_rank", "-scheduled_for", "-id")

        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        target_user_id = int(data.get("user_id") or request.user.id)
        reminders = CalendarReminderService().create_for_users(
            created_by=request.user,
            user_ids=[target_user_id],
            reminder_date=data["reminder_date"],
            reminder_time=data["reminder_time"],
            timezone_name=data["timezone"],
            content=data["content"],
            calendar_event_id=data.get("calendar_event_id"),
        )
        result = CalendarReminderSerializer(reminders[0], context=self.get_serializer_context())
        headers = self.get_success_headers(result.data)
        return Response(result.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()

        serializer = self.get_serializer(instance=instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        calendar_event_id = data["calendar_event_id"] if "calendar_event_id" in data else instance.calendar_event_id

        updated = CalendarReminderService().apply_update(
            reminder=instance,
            reminder_date=data.get("reminder_date", instance.reminder_date),
            reminder_time=data.get("reminder_time", instance.reminder_time),
            timezone_name=data.get("timezone", instance.timezone),
            content=data.get("content", instance.content),
            user_id=data.get("user_id"),
            calendar_event_id=calendar_event_id,
        )
        result = CalendarReminderSerializer(updated, context=self.get_serializer_context())
        return Response(result.data)

    @extend_schema(request=CalendarReminderBulkCreateSerializer, responses={201: CalendarReminderSerializer(many=True)})
    @action(detail=False, methods=["post"], url_path="bulk-create")
    def bulk_create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        reminders = CalendarReminderService().create_for_users(
            created_by=request.user,
            user_ids=data["user_ids"],
            reminder_date=data["reminder_date"],
            reminder_time=data["reminder_time"],
            timezone_name=data["timezone"],
            content=data["content"],
            calendar_event_id=data.get("calendar_event_id"),
        )
        return Response(
            CalendarReminderSerializer(reminders, many=True, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get"], url_path="inbox")
    def inbox(self, request):
        today = timezone.localdate()
        tz = timezone.get_current_timezone()
        today_start = timezone.make_aware(datetime.combine(today, datetime.min.time()), tz)
        today_end = today_start + timedelta(days=1)
        limit = self._safe_positive_int(request.query_params.get("limit"), default=20, minimum=1, maximum=100)

        today_queryset = (
            CalendarReminder.objects.select_related("user", "created_by", "calendar_event")
            .filter(
                user=request.user,
                status=CalendarReminder.STATUS_SENT,
                sent_at__gte=today_start,
                sent_at__lt=today_end,
            )
            .order_by("-sent_at", "-id")
        )
        unread_count = today_queryset.filter(read_at__isnull=True).count()
        payload = CalendarReminderSerializer(
            today_queryset[:limit], many=True, context=self.get_serializer_context()
        ).data
        return Response(
            {
                "date": str(today),
                "unreadCount": unread_count,
                "today": payload,
            }
        )

    @action(detail=False, methods=["post"], url_path="inbox/mark-read")
    def inbox_mark_read(self, request):
        serializer = self.get_serializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data.get("ids") or []
        device_label = (serializer.validated_data.get("device_label") or "").strip()

        today = timezone.localdate()
        tz = timezone.get_current_timezone()
        today_start = timezone.make_aware(datetime.combine(today, datetime.min.time()), tz)
        today_end = today_start + timedelta(days=1)
        now = timezone.now()
        unread_queryset = CalendarReminder.objects.filter(
            user=request.user,
            status=CalendarReminder.STATUS_SENT,
            sent_at__gte=today_start,
            sent_at__lt=today_end,
            read_at__isnull=True,
        )
        target_queryset = unread_queryset.filter(id__in=ids) if ids else unread_queryset
        if device_label:
            updated = target_queryset.update(read_at=now, read_device_label=device_label, updated_at=now)
        else:
            updated = target_queryset.update(read_at=now, updated_at=now)
        unread_count = CalendarReminder.objects.filter(
            user=request.user,
            status=CalendarReminder.STATUS_SENT,
            sent_at__gte=today_start,
            sent_at__lt=today_end,
            read_at__isnull=True,
        ).count()
        return Response({"updated": updated, "unreadCount": unread_count})

    @action(detail=False, methods=["post"], url_path="inbox/snooze")
    def inbox_snooze(self, request):
        serializer = self.get_serializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)

        reminder_id = serializer.validated_data["id"]
        minutes = serializer.validated_data.get("minutes", 15)

        reminder = CalendarReminder.objects.filter(
            id=reminder_id,
            user=request.user,
            status=CalendarReminder.STATUS_SENT,
            read_at__isnull=True,
        ).first()
        if reminder is None:
            return self.error_response("Reminder not found or already handled.", status.HTTP_404_NOT_FOUND)

        reminder_timezone_name = reminder.timezone or CalendarReminder.DEFAULT_TIMEZONE
        try:
            reminder_tz = ZoneInfo(reminder_timezone_name)
        except ZoneInfoNotFoundError:
            reminder_tz = ZoneInfo(CalendarReminder.DEFAULT_TIMEZONE)
            reminder_timezone_name = CalendarReminder.DEFAULT_TIMEZONE

        scheduled_local = timezone.localtime(timezone.now() + timedelta(minutes=minutes), reminder_tz)
        reminder.reminder_date = scheduled_local.date()
        reminder.reminder_time = scheduled_local.time().replace(second=0, microsecond=0)
        reminder.timezone = reminder_timezone_name
        reminder.status = CalendarReminder.STATUS_PENDING
        reminder.sent_at = None
        reminder.read_at = None
        reminder.read_device_label = ""
        reminder.delivery_channel = ""
        reminder.delivery_device_label = ""
        reminder.error_message = ""
        reminder.save(
            update_fields=[
                "reminder_date",
                "reminder_time",
                "timezone",
                "scheduled_for",
                "status",
                "sent_at",
                "read_at",
                "delivery_channel",
                "delivery_device_label",
                "error_message",
                "read_device_label",
                "updated_at",
            ]
        )

        today = timezone.localdate()
        unread_count = CalendarReminder.objects.filter(
            user=request.user,
            status=CalendarReminder.STATUS_SENT,
            sent_at__date=today,
            read_at__isnull=True,
        ).count()

        return Response(
            {
                "id": reminder.id,
                "minutes": minutes,
                "scheduledFor": reminder.scheduled_for.isoformat(),
                "unreadCount": unread_count,
            }
        )

    @action(detail=False, methods=["get"], url_path="users")
    def users(self, request):
        user_query = (request.query_params.get("q") or request.query_params.get("search") or "").strip()
        page = self._safe_positive_int(request.query_params.get("page"), default=1, minimum=1)
        page_size = self._safe_positive_int(request.query_params.get("page_size"), default=20, minimum=1, maximum=100)
        offset = (page - 1) * page_size

        User = get_user_model()
        queryset = (
            User.objects.filter(is_active=True)
            .annotate(
                active_push_subscriptions=Count(
                    "web_push_subscriptions",
                    filter=Q(web_push_subscriptions__is_active=True),
                    distinct=True,
                )
            )
            .order_by("first_name", "last_name", "username")
        )
        if user_query:
            queryset = queryset.filter(
                Q(username__icontains=user_query)
                | Q(email__icontains=user_query)
                | Q(first_name__icontains=user_query)
                | Q(last_name__icontains=user_query)
            )

        users = queryset[offset : offset + page_size]
        payload = [
            {
                "id": user.id,
                "username": user.username,
                "email": user.email or "",
                "full_name": user.get_full_name().strip() or user.username,
                "active_push_subscriptions": int(getattr(user, "active_push_subscriptions", 0) or 0),
            }
            for user in users
        ]
        return Response(payload)

    @action(detail=False, methods=["get"], url_path="timezones")
    def timezones(self, request):
        from zoneinfo import available_timezones

        timezone_query = (request.query_params.get("q") or "").strip().lower()
        page = self._safe_positive_int(request.query_params.get("page"), default=1, minimum=1)
        page_size = self._safe_positive_int(request.query_params.get("page_size"), default=50, minimum=1, maximum=200)
        offset = (page - 1) * page_size

        zones = sorted(available_timezones())
        if timezone_query:
            zones = [zone for zone in zones if timezone_query in zone.lower()]

        window = zones[offset : offset + page_size]
        payload = [{"value": zone, "label": zone} for zone in window]
        return Response(payload)

    @action(detail=True, methods=["post"], url_path="ack")
    def ack(self, request, pk=None):
        """Record delivery channel for a reminder (in_app or system)."""
        reminder = self.get_object()
        channel = (request.data.get("channel") or "").strip()
        device_label = (request.data.get("device_label") or "").strip()
        allowed = {CalendarReminder.DELIVERY_IN_APP, CalendarReminder.DELIVERY_SYSTEM}
        if channel not in allowed:
            return self.error_response(
                f"Invalid channel. Must be one of: {', '.join(sorted(allowed))}",
                status.HTTP_400_BAD_REQUEST,
            )
        update_fields: list[str] = []
        if not reminder.delivery_channel:
            reminder.delivery_channel = channel
            update_fields.append("delivery_channel")
        if device_label and (not reminder.delivery_device_label):
            reminder.delivery_device_label = device_label[:255]
            update_fields.append("delivery_device_label")

        if update_fields:
            reminder.save(update_fields=[*update_fields, "updated_at"])
        return Response(
            {
                "id": reminder.id,
                "delivery_channel": reminder.delivery_channel,
                "delivery_device_label": reminder.delivery_device_label,
            }
        )


class PushNotificationViewSet(ApiErrorHandlingMixin, viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = WebPushSubscriptionSerializer

    def get_serializer_class(self):
        action = getattr(self, "action", None)
        action_map = {
            "subscriptions": WebPushSubscriptionSerializer,
            "register": WebPushSubscriptionUpsertSerializer,
            "unregister": WebPushSubscriptionDeleteSerializer,
            "test": PushNotificationTestSerializer,
            "send_test": AdminPushNotificationSendSerializer,
            "send_test_whatsapp": AdminWhatsappTestSendSerializer,
        }
        return action_map.get(action, self.serializer_class)

    def _ensure_admin(self, request):
        if not request.user or not request.user.is_staff:
            return self.error_response("You do not have permission to perform this action.", status.HTTP_403_FORBIDDEN)
        return None

    @staticmethod
    def _result_payload(result):
        return {
            "sent": result.sent,
            "failed": result.failed,
            "skipped": result.skipped,
            "total": result.total,
        }

    @staticmethod
    def _active_subscription_count(user):
        return WebPushSubscription.objects.filter(user=user, is_active=True).count()

    @staticmethod
    def _subscription_count(user):
        return WebPushSubscription.objects.filter(user=user).count()

    @staticmethod
    def _latest_application_for_test_notification():
        return DocApplication.objects.order_by("-updated_at", "-id").first()

    @action(detail=False, methods=["get"], url_path="subscriptions")
    def subscriptions(self, request):
        queryset = WebPushSubscription.objects.filter(user=request.user).order_by("-updated_at")
        return Response(WebPushSubscriptionSerializer(queryset, many=True).data)

    @action(detail=False, methods=["post"], url_path="register")
    def register(self, request):
        serializer = WebPushSubscriptionUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = cast(dict[str, Any], serializer.validated_data)
        token = data["token"].strip()
        if not token:
            return self.error_response("Token is required", status.HTTP_400_BAD_REQUEST)

        subscription, created = WebPushSubscription.objects.update_or_create(
            token=token,
            defaults={
                "user": request.user,
                "device_label": serializer.validated_data.get("device_label", ""),
                "user_agent": serializer.validated_data.get("user_agent") or request.META.get("HTTP_USER_AGENT", ""),
                "is_active": True,
                "last_error": "",
            },
        )
        payload = WebPushSubscriptionSerializer(subscription).data
        payload["created"] = created
        return Response(payload, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="unregister")
    def unregister(self, request):
        serializer = WebPushSubscriptionDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = cast(dict[str, Any], serializer.validated_data)
        token = data["token"].strip()
        updated = WebPushSubscription.objects.filter(user=request.user, token=token).update(is_active=False)
        return Response({"updated": updated})

    @action(detail=False, methods=["post"], url_path="test")
    def test(self, request):
        serializer = PushNotificationTestSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)

        data = cast(dict[str, Any], serializer.validated_data)
        active_subscriptions = self._active_subscription_count(request.user)
        if active_subscriptions == 0:
            return self.error_response(
                "No active browser push subscriptions for your user. Open CRM in a browser, allow notifications, then retry.",
                status.HTTP_409_CONFLICT,
                details={
                    "active_subscriptions": 0,
                    "total_subscriptions": self._subscription_count(request.user),
                },
            )
        try:
            result = PushNotificationService().send_to_user(
                user=request.user,
                title=data["title"],
                body=data["body"],
                data=data.get("data") or {},
                link=(data.get("link") or "").strip() or None,
            )
        except FcmConfigurationError as exc:
            return self.error_response(str(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)

        payload = self._result_payload(result)
        if result.sent == 0:
            return self.error_response(
                "Push delivery failed for all active subscriptions.",
                status.HTTP_502_BAD_GATEWAY,
                details=payload,
            )
        return Response(payload)

    @action(detail=False, methods=["get"], url_path="users")
    def users(self, request):
        forbidden = self._ensure_admin(request)
        if forbidden is not None:
            return forbidden

        from django.contrib.auth import get_user_model

        User = get_user_model()
        queryset = (
            User.objects.filter(is_active=True)
            .annotate(
                total_push_subscriptions=Count("web_push_subscriptions", distinct=True),
                active_push_subscriptions=Count(
                    "web_push_subscriptions",
                    filter=Q(web_push_subscriptions__is_active=True),
                    distinct=True,
                ),
            )
            .order_by("username")
        )
        payload = [
            {
                "id": user.id,
                "username": user.username,
                "email": user.email or "",
                "full_name": (f"{user.first_name} {user.last_name}".strip() or user.username),
                "active_push_subscriptions": int(getattr(user, "active_push_subscriptions", 0) or 0),
                "total_push_subscriptions": int(getattr(user, "total_push_subscriptions", 0) or 0),
            }
            for user in queryset
        ]
        return Response(payload)

    @action(detail=False, methods=["post"], url_path="send-test")
    def send_test(self, request):
        forbidden = self._ensure_admin(request)
        if forbidden is not None:
            return forbidden

        from django.contrib.auth import get_user_model

        serializer = AdminPushNotificationSendSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        data = cast(dict[str, Any], serializer.validated_data)

        User = get_user_model()
        target_user = User.objects.filter(pk=data["user_id"], is_active=True).first()
        if not target_user:
            return self.error_response("Target user not found", status.HTTP_404_NOT_FOUND)

        active_subscriptions = self._active_subscription_count(target_user)
        if active_subscriptions == 0:
            return self.error_response(
                "Target user has no active browser push subscriptions. Open CRM in browser, allow notifications, then retry.",
                status.HTTP_409_CONFLICT,
                details={
                    "target_user_id": target_user.id,
                    "active_subscriptions": 0,
                    "total_subscriptions": self._subscription_count(target_user),
                },
            )

        try:
            result = PushNotificationService().send_to_user(
                user=target_user,
                title=data["title"],
                body=data["body"],
                data=data.get("data") or {},
                link=(data.get("link") or "").strip() or None,
            )
        except FcmConfigurationError as exc:
            return self.error_response(str(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)

        payload = self._result_payload(result)
        if result.sent == 0:
            return self.error_response(
                "Push delivery failed for all active subscriptions of the target user.",
                status.HTTP_502_BAD_GATEWAY,
                details=payload,
            )
        return Response(payload)

    @action(detail=False, methods=["post"], url_path="send-test-whatsapp")
    def send_test_whatsapp(self, request):
        forbidden = self._ensure_admin(request)
        if forbidden is not None:
            return forbidden

        serializer = AdminWhatsappTestSendSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        explicit_recipient = str(data.get("to") or "").strip()
        recipient = explicit_recipient or str(getattr(settings, "WHATSAPP_TEST_NUMBER", "") or "").strip()
        if not recipient:
            return self.error_response(
                "No WhatsApp destination configured. Set WHATSAPP_TEST_NUMBER in backend settings or provide 'to'.",
                status.HTTP_400_BAD_REQUEST,
            )

        target_application = self._latest_application_for_test_notification()
        if target_application is None:
            return self.error_response(
                "No applications available to attach a dummy workflow notification.",
                status.HTTP_409_CONFLICT,
            )

        from customer_applications.tasks import schedule_whatsapp_status_poll
        from notifications.services.providers import WhatsappNotificationProvider, is_queued_provider_result

        subject = str(data.get("subject") or "").strip() or "Revis Bali CRM WhatsApp Test"
        body = str(data.get("body") or "").strip() or "WhatsApp test message from Revis Bali CRM."
        whatsapp_body = f"{subject}\n\n{body}" if subject else body

        try:
            message_id = WhatsappNotificationProvider().send(
                recipient=recipient,
                subject=subject,
                body=whatsapp_body,
                prefer_template=False,
                allow_template_fallback=False,
            )
        except Exception as exc:
            return self.error_response(
                f"WhatsApp text send failed: {exc}. "
                "Template fallback is disabled for this test endpoint to preserve exact subject/body.",
                status.HTTP_400_BAD_REQUEST,
            )

        raw_message_id = str(message_id or "").strip()
        queued = is_queued_provider_result("whatsapp", raw_message_id)
        notification = WorkflowNotification.objects.create(
            channel=WorkflowNotification.CHANNEL_WHATSAPP,
            recipient=recipient,
            subject=subject,
            body=body,
            doc_application=target_application,
            doc_workflow=None,
            status=WorkflowNotification.STATUS_PENDING,
            provider_message=raw_message_id,
            external_reference="" if queued else raw_message_id,
            sent_at=None,
            scheduled_for=timezone.now(),
            notification_type="manual_whatsapp_test",
        )
        if notification.external_reference:
            schedule_whatsapp_status_poll(notification_id=notification.id, delay_seconds=5)

        return Response(
            {
                "recipient": recipient,
                "used_default_recipient": explicit_recipient == "",
                "message_id": raw_message_id,
                "workflow_notification_id": notification.id,
                "workflow_notification_status": notification.status,
                "workflow_notification_application_id": notification.doc_application_id,
            }
        )

    @action(detail=False, methods=["post"], url_path="fcm-register-proxy")
    def fcm_register_proxy(self, request):
        """
        Server-side proxy for Firebase Cloud Messaging registration.

        The browser-side Firebase SDK calls fcmregistrations.googleapis.com to exchange
        a Web Push subscription for an FCM token.  On some networks / Chrome configurations
        that endpoint is unreachable from the browser (e.g. QUIC / HTTP3 issues) even
        though the Django server can reach it fine via TCP.  This action forwards the
        registration request from the browser to the real FCM endpoint server-side so the
        browser never needs to reach googleapis.com directly.
        """
        import requests as http_requests

        project_id = getattr(settings, "FCM_PROJECT_ID", "").strip()
        if not project_id:
            return self.error_response("FCM_PROJECT_ID not configured on server", status.HTTP_503_SERVICE_UNAVAILABLE)

        # The Angular fetch interceptor forwards the FIS auth token via X-FCM-Auth.
        # Firebase SDK uses x-goog-firebase-installations-auth (not Authorization).
        fcm_auth = request.META.get("HTTP_X_FCM_AUTH", "").strip()
        api_key = (
            request.META.get("HTTP_X_GOOG_API_KEY", "").strip() or getattr(settings, "FCM_WEB_API_KEY", "").strip()
        )

        if not api_key:
            return self.error_response(
                "Missing required proxy header: X-Goog-Api-Key (and FCM_WEB_API_KEY not configured)",
                status.HTTP_400_BAD_REQUEST,
            )

        url = f"https://fcmregistrations.googleapis.com/v1/projects/{project_id}/registrations"
        fwd_headers: dict = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
        if fcm_auth:
            fwd_headers["x-goog-firebase-installations-auth"] = fcm_auth
        try:
            # Use request.body (raw bytes) instead of request.data to avoid
            # DRF's camelCase→snake_case parser corrupting field names.
            resp = http_requests.post(
                url,
                data=request.body,
                headers=fwd_headers,
                timeout=20,
            )
        except http_requests.RequestException as exc:
            logger.error("[fcm_register_proxy] Network error calling FCM registrations: %s", exc)
            return self.error_response(str(exc), status.HTTP_502_BAD_GATEWAY)

        try:
            body = resp.json()
        except ValueError:
            body = {"raw": resp.text}

        return Response(body, status=resp.status_code)

    @action(detail=False, methods=["post"], url_path="firebase-install-proxy")
    def firebase_install_proxy(self, request):
        """
        Server-side proxy for Firebase Installations API.

        Handles both FID creation (POST .../installations) and auth-token refresh
        (POST .../installations/{fid}/authTokens:generate) so the browser is never
        required to reach firebaseinstallations.googleapis.com directly.
        """
        import requests as http_requests

        project_id = getattr(settings, "FCM_PROJECT_ID", "").strip()
        if not project_id:
            return self.error_response("FCM_PROJECT_ID not configured on server", status.HTTP_503_SERVICE_UNAVAILABLE)

        # The Angular fetch interceptor passes the original path suffix via a custom header.
        path_suffix = request.META.get("HTTP_X_FIREBASE_PATH", "").strip().lstrip("/")
        api_key = (
            request.META.get("HTTP_X_GOOG_API_KEY", "").strip() or getattr(settings, "FCM_WEB_API_KEY", "").strip()
        )
        firebase_auth = request.META.get("HTTP_X_FIREBASE_AUTH", "").strip()

        if not api_key:
            return self.error_response("Missing required proxy header: X-Goog-Api-Key", status.HTTP_400_BAD_REQUEST)

        base = f"https://firebaseinstallations.googleapis.com/v1/projects/{project_id}"
        url = f"{base}/{path_suffix}" if path_suffix else base

        headers: dict = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
        if firebase_auth:
            headers["x-goog-firebase-installations-auth"] = firebase_auth

        try:
            # Use request.body (raw bytes) instead of request.data to avoid
            # DRF's camelCase→snake_case parser corrupting field names.
            resp = http_requests.post(url, data=request.body, headers=headers, timeout=20)
        except http_requests.RequestException as exc:
            logger.error("[firebase_install_proxy] Network error calling Firebase Installations: %s", exc)
            return self.error_response(str(exc), status.HTTP_502_BAD_GATEWAY)

        try:
            body = resp.json()
        except ValueError:
            body = {"raw": resp.text}

        return Response(body, status=resp.status_code)


@sse_token_auth_required
def calendar_reminders_stream_sse(request):
    """SSE endpoint for calendar reminder list live updates."""
    user = request.user
    if not (user and user.is_authenticated):
        return JsonResponse({"error": "Authentication required"}, status=403)

    def _latest_reminder_state():
        latest = (
            CalendarReminder.objects.filter(created_by=user)
            .order_by("-updated_at", "-id")
            .values("id", "updated_at")
            .first()
        )
        if not latest:
            return None, None
        updated_at = latest.get("updated_at")
        return latest.get("id"), updated_at.isoformat() if updated_at else None

    def _build_payload(
        *,
        event: str,
        cursor: str,
        last_reminder_id,
        last_updated_at,
        reason: str,
        operation=None,
        changed_reminder_id=None,
    ):
        payload = {
            "event": event,
            "cursor": cursor,
            "lastReminderId": last_reminder_id,
            "lastUpdatedAt": last_updated_at,
            "reason": reason,
        }
        if operation:
            payload["operation"] = operation
        if changed_reminder_id is not None:
            payload["changedReminderId"] = changed_reminder_id
        return payload

    def event_stream():
        stream_key = stream_user_key(user.id)
        replay_cursor = resolve_last_event_id(request)
        current_cursor = replay_cursor or "0-0"
        last_reminder_id, last_updated_at = _latest_reminder_state()
        fallback_refresh_interval_seconds = 1.0
        last_fallback_refresh_at = time.monotonic()

        snapshot_payload = _build_payload(
            event="calendar_reminders_snapshot",
            cursor=current_cursor,
            last_reminder_id=last_reminder_id,
            last_updated_at=last_updated_at,
            reason="initial",
        )
        yield format_sse_event(data=snapshot_payload)

        for stream_event in iter_replay_and_live_events(
            stream_key=stream_key,
            last_event_id=replay_cursor,
            block_ms=1_000,
        ):
            try:
                if stream_event is None:
                    yield ": keepalive\n\n"
                    now = time.monotonic()
                    if (now - last_fallback_refresh_at) >= fallback_refresh_interval_seconds:
                        current_reminder_id, current_last_updated_at = _latest_reminder_state()
                        if (current_reminder_id, current_last_updated_at) != (last_reminder_id, last_updated_at):
                            payload = _build_payload(
                                event="calendar_reminders_changed",
                                cursor=current_cursor,
                                last_reminder_id=current_reminder_id,
                                last_updated_at=current_last_updated_at,
                                reason="db_state_change",
                            )
                            yield format_sse_event(data=payload)
                            last_reminder_id = current_reminder_id
                            last_updated_at = current_last_updated_at
                        last_fallback_refresh_at = now
                    continue

                event_meta = stream_event.payload if isinstance(stream_event.payload, dict) else {}
                operation = str(event_meta.get("operation") or "").strip() or None
                raw_changed_id = event_meta.get("reminderId")
                try:
                    changed_reminder_id = int(raw_changed_id) if raw_changed_id is not None else None
                except (TypeError, ValueError):
                    changed_reminder_id = None

                current_reminder_id, current_last_updated_at = _latest_reminder_state()
                payload = _build_payload(
                    event="calendar_reminders_changed",
                    cursor=stream_event.id,
                    last_reminder_id=current_reminder_id,
                    last_updated_at=current_last_updated_at,
                    reason="signal",
                    operation=operation,
                    changed_reminder_id=changed_reminder_id,
                )
                yield format_sse_event(event_id=stream_event.id, data=payload)
                current_cursor = stream_event.id
                last_reminder_id = current_reminder_id
                last_updated_at = current_last_updated_at
                last_fallback_refresh_at = time.monotonic()
            except GeneratorExit:
                return
            except Exception as exc:
                yield format_sse_event(data={"event": "calendar_reminders_error", "error": str(exc)})
                return

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@sse_token_auth_required
def workflow_notifications_stream_sse(request):
    """SSE endpoint for workflow notification center live updates."""
    user = request.user
    if not is_staff_or_admin_group(user):
        return JsonResponse({"error": STAFF_OR_ADMIN_PERMISSION_REQUIRED_ERROR}, status=403)

    def _latest_recent_notification_state():
        cutoff = timezone.now() - timedelta(hours=RECENT_WORKFLOW_NOTIFICATION_WINDOW_HOURS)
        latest = (
            WorkflowNotification.objects.filter(created_at__gte=cutoff)
            .order_by("-updated_at", "-id")
            .values("id", "updated_at")
            .first()
        )
        if not latest:
            return None, None
        updated_at = latest.get("updated_at")
        return latest.get("id"), updated_at.isoformat() if updated_at else None

    def _build_payload(
        *,
        event: str,
        cursor: str,
        last_notification_id,
        last_updated_at,
        reason: str,
        operation=None,
        changed_notification_id=None,
    ):
        payload = {
            "event": event,
            "cursor": cursor,
            "windowHours": RECENT_WORKFLOW_NOTIFICATION_WINDOW_HOURS,
            "lastNotificationId": last_notification_id,
            "lastUpdatedAt": last_updated_at,
            "reason": reason,
        }
        if operation:
            payload["operation"] = operation
        if changed_notification_id is not None:
            payload["changedNotificationId"] = changed_notification_id
        return payload

    def event_stream():
        stream_key = stream_job_key("workflow-notifications")
        replay_cursor = resolve_last_event_id(request)
        current_cursor = replay_cursor or "0-0"
        last_notification_id, last_updated_at = _latest_recent_notification_state()
        fallback_refresh_interval_seconds = 1.0
        last_fallback_refresh_at = time.monotonic()

        snapshot_payload = _build_payload(
            event="workflow_notifications_snapshot",
            cursor=current_cursor,
            last_notification_id=last_notification_id,
            last_updated_at=last_updated_at,
            reason="initial",
        )
        yield format_sse_event(data=snapshot_payload)

        for stream_event in iter_replay_and_live_events(
            stream_key=stream_key,
            last_event_id=replay_cursor,
            block_ms=1_000,
        ):
            try:
                if stream_event is None:
                    yield ": keepalive\n\n"
                    now = time.monotonic()
                    if (now - last_fallback_refresh_at) >= fallback_refresh_interval_seconds:
                        current_notification_id, current_last_updated_at = _latest_recent_notification_state()
                        if (current_notification_id, current_last_updated_at) != (
                            last_notification_id,
                            last_updated_at,
                        ):
                            payload = _build_payload(
                                event="workflow_notifications_changed",
                                cursor=current_cursor,
                                last_notification_id=current_notification_id,
                                last_updated_at=current_last_updated_at,
                                reason="db_state_change",
                            )
                            yield format_sse_event(data=payload)
                            last_notification_id = current_notification_id
                            last_updated_at = current_last_updated_at
                        last_fallback_refresh_at = now
                    continue

                event_meta = stream_event.payload if isinstance(stream_event.payload, dict) else {}
                operation = str(event_meta.get("operation") or "").strip() or None
                raw_changed_id = event_meta.get("notificationId")
                changed_notification_id = None
                if raw_changed_id is not None:
                    try:
                        changed_notification_id = int(raw_changed_id)
                    except (TypeError, ValueError):
                        changed_notification_id = None

                current_notification_id, current_last_updated_at = _latest_recent_notification_state()
                payload = _build_payload(
                    event="workflow_notifications_changed",
                    cursor=stream_event.id,
                    last_notification_id=current_notification_id,
                    last_updated_at=current_last_updated_at,
                    reason="signal",
                    operation=operation,
                    changed_notification_id=changed_notification_id,
                )
                yield format_sse_event(event_id=stream_event.id, data=payload)
                current_cursor = stream_event.id
                last_notification_id = current_notification_id
                last_updated_at = current_last_updated_at
                last_fallback_refresh_at = time.monotonic()
            except GeneratorExit:
                return
            except Exception as exc:
                yield format_sse_event(data={"event": "workflow_notifications_error", "error": str(exc)})
                return

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@sse_token_auth_required
def async_job_status_sse(request, job_id):
    """Generic SSE endpoint for tracking AsyncJob status."""
    job_queryset = restrict_to_owner_unless_privileged(AsyncJob.objects.filter(id=job_id), request.user)
    if not job_queryset.exists():
        return JsonResponse({"error": "Job not found"}, status=404)

    def event_stream():
        replay_cursor = resolve_last_event_id(request)
        stream_key = stream_job_key(job_id)
        last_progress = None
        last_status = None

        try:
            job = job_queryset.get()
        except AsyncJob.DoesNotExist:
            yield format_sse_event(data={"error": "Job not found"})
            return

        initial_payload = serialize_async_job_payload(job)
        yield format_sse_event(data=initial_payload)
        last_progress = job.progress
        last_status = job.status
        if job.status in [AsyncJob.STATUS_COMPLETED, AsyncJob.STATUS_FAILED]:
            return

        for stream_event in iter_replay_and_live_events(stream_key=stream_key, last_event_id=replay_cursor):
            try:
                if stream_event is None:
                    yield ": keepalive\n\n"
                    continue

                data = normalize_async_job_payload(stream_event.payload)
                if data is None or data["status"] in [AsyncJob.STATUS_COMPLETED, AsyncJob.STATUS_FAILED]:
                    job = job_queryset.get()
                    data = serialize_async_job_payload(job)

                if data["progress"] == last_progress and data["status"] == last_status:
                    continue

                yield format_sse_event(event_id=stream_event.id, data=data)
                last_progress = data["progress"]
                last_status = data["status"]

                if data["status"] in [AsyncJob.STATUS_COMPLETED, AsyncJob.STATUS_FAILED]:
                    return
            except AsyncJob.DoesNotExist:
                yield format_sse_event(data={"error": "Job not found"})
                break
            except Exception as e:
                yield format_sse_event(data={"error": str(e)})
                break

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


class AsyncJobViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for polling AsyncJob status if SSE is not used."""

    queryset = AsyncJob.objects.all()
    serializer_class = AsyncJobSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return restrict_to_owner_unless_privileged(super().get_queryset(), self.request.user)
