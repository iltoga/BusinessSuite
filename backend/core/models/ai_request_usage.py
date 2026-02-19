from django.db import models


class AIRequestUsage(models.Model):
    """
    Compact accounting log for one LLM request.

    We intentionally avoid storing prompts/responses to keep storage lean and reduce
    sensitive-data retention risk.
    """

    feature = models.CharField(max_length=120, db_index=True)
    provider = models.CharField(max_length=32, db_index=True)
    model = models.CharField(max_length=160, db_index=True)
    request_type = models.CharField(max_length=32, default="chat.completions", db_index=True)
    request_id = models.CharField(max_length=120, blank=True, null=True, db_index=True)

    success = models.BooleanField(default=True, db_index=True)
    error_type = models.CharField(max_length=64, blank=True)
    latency_ms = models.PositiveIntegerField(blank=True, null=True)

    prompt_tokens = models.PositiveIntegerField(blank=True, null=True)
    completion_tokens = models.PositiveIntegerField(blank=True, null=True)
    total_tokens = models.PositiveIntegerField(blank=True, null=True)
    cached_prompt_tokens = models.PositiveIntegerField(blank=True, null=True)
    cache_write_tokens = models.PositiveIntegerField(blank=True, null=True)
    reasoning_tokens = models.PositiveIntegerField(blank=True, null=True)

    cost_usd = models.DecimalField(max_digits=12, decimal_places=6, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["feature", "created_at"]),
            models.Index(fields=["provider", "created_at"]),
            models.Index(fields=["model", "created_at"]),
        ]

    def __str__(self) -> str:
        status = "ok" if self.success else "err"
        return f"{self.feature} [{self.provider}/{self.model}] ({status})"
