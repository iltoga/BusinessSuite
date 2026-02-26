from __future__ import annotations

import secrets

from api.permissions import is_superuser_or_admin_group
from core.models.local_resilience import LocalResilienceSettings, SyncChangeLog, SyncConflict, SyncCursor
from core.services.sync_service import (
    fetch_media_entries,
    get_local_node_id,
    get_media_manifest,
    ingest_remote_changes,
    pull_changes,
    refresh_media_manifest,
)
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.dateparse import parse_datetime
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import AccessToken

User = get_user_model()


class SyncPlaceholderSerializer(serializers.Serializer):
    """Schema placeholder for sync utility endpoints."""


class SyncViewSet(viewsets.ViewSet):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes: list = []
    serializer_class = SyncPlaceholderSerializer

    def _extract_header_token(self, request) -> str | None:
        auth_header = (request.META.get("HTTP_AUTHORIZATION") or "").strip()
        if not auth_header:
            return None
        parts = auth_header.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() in {"bearer", "token"}:
            token = parts[1].strip()
            return token or None
        return auth_header

    def _resolve_user_from_token(self, token_str: str | None):
        if not token_str:
            return None

        if token_str.startswith("eyJ"):
            try:
                access_token = AccessToken(token_str)
                user_id = access_token.get("user_id")
                if user_id is None:
                    return None
                return User.objects.filter(pk=user_id).first()
            except Exception:
                pass

        try:
            token = Token.objects.select_related("user").filter(key=token_str).first()
            return token.user if token else None
        except Exception:
            return None

    def _has_sync_service_token(self, token_str: str | None) -> bool:
        configured = str(getattr(settings, "LOCAL_SYNC_REMOTE_TOKEN", "") or "").strip()
        if not configured or not token_str:
            return False
        return secrets.compare_digest(configured, token_str)

    def _authorize(self, request):
        if request.user and request.user.is_authenticated and is_superuser_or_admin_group(request.user):
            return None

        token_str = self._extract_header_token(request)
        if not token_str:
            return Response({"detail": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

        if self._has_sync_service_token(token_str):
            return None

        token_user = self._resolve_user_from_token(token_str)
        if token_user and token_user.is_active and is_superuser_or_admin_group(token_user):
            request.user = token_user
            return None

        return Response({"detail": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

    @extend_schema(summary="Get sync state", responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["get"], url_path="state")
    def state(self, request):
        auth_error = self._authorize(request)
        if auth_error is not None:
            return auth_error

        last_seq = SyncChangeLog.objects.order_by("-seq").values_list("seq", flat=True).first() or 0
        pending_conflicts = SyncConflict.objects.filter(status=SyncConflict.STATUS_PENDING).count()
        settings_obj = LocalResilienceSettings.get_solo()
        remote_cursor = SyncCursor.objects.filter(node_id="remote").first()

        return Response(
            {
                "nodeId": get_local_node_id(),
                "lastSeq": int(last_seq),
                "pendingConflicts": int(pending_conflicts),
                "syncEnabled": bool(getattr(settings, "LOCAL_SYNC_ENABLED", False) and settings_obj.enabled),
                "remoteCursor": {
                    "lastPulledSeq": int(remote_cursor.last_pulled_seq) if remote_cursor else 0,
                    "lastPushedSeq": int(remote_cursor.last_pushed_seq) if remote_cursor else 0,
                    "lastPulledAt": (
                        remote_cursor.last_pulled_at.isoformat()
                        if remote_cursor and remote_cursor.last_pulled_at
                        else None
                    ),
                    "lastPushedAt": (
                        remote_cursor.last_pushed_at.isoformat()
                        if remote_cursor and remote_cursor.last_pushed_at
                        else None
                    ),
                    "lastError": remote_cursor.last_error if remote_cursor else "",
                    "updatedAt": (
                        remote_cursor.updated_at.isoformat() if remote_cursor and remote_cursor.updated_at else None
                    ),
                },
            }
        )

    @extend_schema(summary="Push sync changes", responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["post"], url_path="changes/push")
    def push_changes(self, request):
        auth_error = self._authorize(request)
        if auth_error is not None:
            return auth_error

        body = request.data if isinstance(request.data, dict) else {}
        source_node = str(body.get("source_node") or body.get("sourceNode") or "unknown-remote").strip()
        changes = body.get("changes") if isinstance(body.get("changes"), list) else []

        result = ingest_remote_changes(source_node=source_node, changes=changes)
        return Response(result)

    @extend_schema(
        summary="Pull sync changes",
        parameters=[
            OpenApiParameter("after_seq", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("limit", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["get"], url_path="changes/pull")
    def pull_changes_endpoint(self, request):
        auth_error = self._authorize(request)
        if auth_error is not None:
            return auth_error

        try:
            after_seq = int(request.query_params.get("after_seq", "0"))
        except ValueError:
            after_seq = 0
        try:
            limit = int(request.query_params.get("limit", "200"))
        except ValueError:
            limit = 200

        changes = pull_changes(after_seq=after_seq, limit=min(max(1, limit), 1000))
        next_seq = max((int(item.get("seq") or 0) for item in changes), default=after_seq)
        return Response(
            {
                "changes": changes,
                "count": len(changes),
                "nextSeq": next_seq,
            }
        )

    @extend_schema(
        summary="Get media manifest",
        parameters=[
            OpenApiParameter("after_updated_at", OpenApiTypes.DATETIME, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("limit", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["get"], url_path="media/manifest")
    def media_manifest(self, request):
        auth_error = self._authorize(request)
        if auth_error is not None:
            return auth_error

        after_raw = request.query_params.get("after_updated_at")
        after_updated_at = parse_datetime(after_raw) if after_raw else None
        try:
            limit = int(request.query_params.get("limit", "500"))
        except ValueError:
            limit = 500

        refreshed = refresh_media_manifest()
        items = get_media_manifest(after_updated_at=after_updated_at, limit=min(max(1, limit), 2000))
        return Response({"refreshed": int(refreshed), "items": items, "count": len(items)})

    @extend_schema(summary="Fetch media entries", responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["post"], url_path="media/fetch")
    def media_fetch(self, request):
        auth_error = self._authorize(request)
        if auth_error is not None:
            return auth_error

        body = request.data if isinstance(request.data, dict) else {}
        raw_paths = body.get("paths")
        paths = raw_paths if isinstance(raw_paths, list) else ([] if raw_paths is None else [raw_paths])
        include_content = bool(body.get("include_content") or body.get("includeContent"))
        try:
            content_size_limit = int(body.get("content_size_limit") or body.get("contentSizeLimit") or 5_000_000)
        except ValueError:
            content_size_limit = 5_000_000

        items = fetch_media_entries(
            paths=[str(path) for path in (paths or [])],
            include_content=include_content,
            content_size_limit=max(1024, content_size_limit),
        )
        return Response({"items": items, "count": len(items)})
