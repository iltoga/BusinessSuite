#!/usr/bin/env python3
import json
import os
import time
import uuid

import django
import requests

os.environ["DJANGO_SETTINGS_MODULE"] = "business_suite.settings"
django.setup()
import logging

from django.conf import settings as django_settings

from core.audit_handlers import PersistentLokiBackend

LOKI_URL = os.getenv("LOKI_URL", "http://localhost:3100")
unique = f"e2e_loki_test:{uuid.uuid4()}"
backend = PersistentLokiBackend()

loki_handler = None
for h in logging.getLogger("audit").handlers:
    if h.__class__.__name__ == "FailSafeLokiHandler":
        loki_handler = h
        break

sent = {"ok": False}


class _TestLokiPrimary:
    def __init__(self, url, tags=None):
        self.url = url.rstrip("/")
        self.tags = tags or {}

    def emit(self, record):
        sent["ok"] = True
        ts = str(int(time.time() * 1e9))
        msg = record.getMessage()
        payload = {"streams": [{"stream": dict(self.tags or {}), "values": [[ts, msg]]}]}
        push_endpoint = (
            self.url if self.url.endswith("/loki/api/v1/push") else f"{self.url.rstrip('/')}/loki/api/v1/push"
        )
        try:
            resp = requests.post(push_endpoint, json=payload, timeout=2)
            sent["status"] = getattr(resp, "status_code", None)
            sent["text"] = getattr(resp, "text", "")[:200]
        except Exception as exc:
            sent["status"] = None
            sent["error"] = str(exc)


if loki_handler is not None:
    tags = getattr(django_settings, "LOKI_APPLICATION", "business_suite")
    loki_handler._primary = _TestLokiPrimary(LOKI_URL, tags={"application": tags})

print("unique:", unique)
backend._emit_async(
    "info", json.dumps({"event_type": "e2e_test", "msg": unique}), extra={"source": "e2e_test", "audit": False}
)

# wait for send
timeout_wait = time.time() + 5
while time.time() < timeout_wait and not sent.get("ok"):
    time.sleep(0.1)

print("sent:", sent)

# Query Loki
if sent.get("status") not in (200, 204):
    print("handler status not 200/204; attempting direct push")
    ts = str(int(time.time() * 1e9))
    payload = {"streams": [{"stream": {"job": "e2e-test"}, "values": [[ts, unique]]}]}
    push_endpoint = LOKI_URL if LOKI_URL.endswith("/loki/api/v1/push") else f"{LOKI_URL.rstrip('/')}/loki/api/v1/push"
    resp = requests.post(push_endpoint, json=payload)
    print("direct push status", resp.status_code)

# query
end_ns = int(time.time() * 1e9)
start_ns = end_ns - int(60 * 1e9)
# normalize base
if LOKI_URL.endswith("/loki/api/v1/push"):
    loki_base = LOKI_URL[: -len("/loki/api/v1/push")]
else:
    loki_base = LOKI_URL.rstrip("/")
query_endpoint = f"{loki_base}/loki/api/v1/query_range"
resp = requests.get(query_endpoint, params={"query": '{} |= "' + unique + '"', "start": start_ns, "end": end_ns})
print("query status", resp.status_code)
try:
    print("query json:", resp.json())
except Exception as e:
    print("json error", e, "text:", resp.text[:400])
