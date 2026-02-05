#!/usr/bin/env python3
"""Quick helper: emit a test audit event and instruct where to find logs.

This script no longer exercises Loki directly. Instead it emits a structured
audit event via `PersistentLokiBackend` which writes to `logs/audit.log`.
Run and then inspect that file (or check Grafana Alloy if configured to scrape
logs) to verify ingestion.
"""
import json
import os
import time
import uuid

import django

os.environ["DJANGO_SETTINGS_MODULE"] = "business_suite.settings"
django.setup()

from core.audit_handlers import PersistentLokiBackend

unique = f"e2e_audit_test:{uuid.uuid4()}"
backend = PersistentLokiBackend()
print("Emitting test payload:", unique)
backend._emit_async(
    "info", json.dumps({"event_type": "e2e_test", "msg": unique}), extra={"source": "e2e_test", "audit": False}
)
print("Done. Check logs/audit.log or your Grafana Alloy configuration for ingestion.")
