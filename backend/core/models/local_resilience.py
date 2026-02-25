from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

User = get_user_model()


class LocalResilienceSettings(models.Model):
    MODE_LOCAL_PRIMARY = "local_primary"
    MODE_REMOTE_PRIMARY = "remote_primary"

    MODE_CHOICES = [
        (MODE_LOCAL_PRIMARY, "Local Primary"),
        (MODE_REMOTE_PRIMARY, "Remote Primary"),
    ]

    singleton_key = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    enabled = models.BooleanField(default=False)
    encryption_required = models.BooleanField(default=True)
    desktop_mode = models.CharField(max_length=32, choices=MODE_CHOICES, default=MODE_LOCAL_PRIMARY)
    vault_epoch = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_local_resilience_settings",
    )

    class Meta:
        verbose_name = "Local Resilience Settings"
        verbose_name_plural = "Local Resilience Settings"

    def __str__(self) -> str:
        status = "enabled" if self.enabled else "disabled"
        return f"Local resilience ({status})"

    @classmethod
    def get_solo(cls) -> "LocalResilienceSettings":
        settings_obj, _ = cls.objects.get_or_create(singleton_key=1)
        return settings_obj


class SyncChangeLog(models.Model):
    OP_UPSERT = "upsert"
    OP_DELETE = "delete"
    OPERATION_CHOICES = [
        (OP_UPSERT, "Upsert"),
        (OP_DELETE, "Delete"),
    ]

    seq = models.BigAutoField(primary_key=True)
    source_node = models.CharField(max_length=64, db_index=True)
    model_label = models.CharField(max_length=128, db_index=True)
    object_pk = models.CharField(max_length=128, db_index=True)
    operation = models.CharField(max_length=16, choices=OPERATION_CHOICES)
    payload = models.JSONField(default=dict, blank=True)
    source_timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    checksum = models.CharField(max_length=64, blank=True, default="")
    applied = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["seq"]
        indexes = [
            models.Index(fields=["model_label", "object_pk", "seq"], name="syncchg_model_obj_seq_idx"),
            models.Index(fields=["source_node", "seq"], name="syncchg_src_seq_idx"),
            models.Index(fields=["source_timestamp", "seq"], name="syncchg_ts_seq_idx"),
        ]

    def __str__(self) -> str:
        return f"[{self.seq}] {self.model_label}:{self.object_pk} ({self.operation})"


class SyncCursor(models.Model):
    node_id = models.CharField(max_length=64, unique=True)
    last_pulled_seq = models.BigIntegerField(default=0)
    last_pushed_seq = models.BigIntegerField(default=0)
    last_pulled_at = models.DateTimeField(null=True, blank=True)
    last_pushed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["node_id"]

    def __str__(self) -> str:
        return f"Cursor<{self.node_id}> pull={self.last_pulled_seq} push={self.last_pushed_seq}"


class SyncConflict(models.Model):
    STATUS_PENDING = "pending"
    STATUS_REVIEWED = "reviewed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_REVIEWED, "Reviewed"),
    ]

    model_label = models.CharField(max_length=128, db_index=True)
    object_pk = models.CharField(max_length=128, db_index=True)
    incoming_change = models.JSONField(default=dict, blank=True)
    existing_snapshot = models.JSONField(default=dict, blank=True)
    chosen_source = models.CharField(max_length=32, default="existing")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    reason = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"Conflict<{self.model_label}:{self.object_pk}>"


class MediaManifestEntry(models.Model):
    path = models.CharField(max_length=512, unique=True)
    checksum = models.CharField(max_length=64)
    size = models.BigIntegerField(default=0)
    modified_at = models.DateTimeField(default=timezone.now)
    encrypted = models.BooleanField(default=True)
    storage_backend = models.CharField(max_length=255, blank=True, default="")
    source_node = models.CharField(max_length=64, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["path"]
        indexes = [
            models.Index(fields=["updated_at", "path"], name="mediamani_updated_path_idx"),
        ]

    def __str__(self) -> str:
        return self.path
