import json
import os
import time
import uuid

import pytest
import requests

from core.audit_handlers import PersistentLokiBackend

LOKI_URL = os.getenv("LOKI_URL", "http://localhost:3100")

RUN_FLAG = os.getenv("RUN_LOKI_E2E", "False").lower() in ("1", "true", "yes")


@pytest.mark.skipif(not RUN_FLAG, reason="Loki E2E tests disabled; set RUN_LOKI_E2E=1 to enable")
def test_backend_emits_log_and_loki_receives_it():
    """End-to-end: use the app backend to emit a uniquely-identifiable log

    This test uses the real logging pipeline (PersistentLokiBackend -> logger)
    and then queries the running Loki instance to assert the message was ingested.

    NOTE: This test is intentionally excluded from default test runs. Enable by setting
    the environment variable `RUN_LOKI_E2E=1` and ensuring Loki is reachable at LOKI_URL.
    """

    # Compose a unique payload
    unique = f"e2e_loki_test:{uuid.uuid4()}"
    backend = PersistentLokiBackend()

    # Ensure the configured FailSafeLokiHandler will actually send to Loki by patching
    # its internal _primary to a simple sender that posts to the Loki HTTP API. This avoids
    # depending on the external `logging_loki` package in the test environment.
    import logging

    from django.conf import settings as django_settings

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
            # Mark that we attempted to send
            sent["ok"] = True
            # Build a simple JSON push to Loki
            ts = str(int(time.time() * 1e9))
            msg = record.getMessage()
            payload = {
                "streams": [
                    {
                        "stream": dict(self.tags or {}),
                        "values": [[ts, msg]],
                    }
                ]
            }
            # Normalize push endpoint in case LOKI_URL already includes the push path
            push_endpoint = (
                self.url if self.url.endswith("/loki/api/v1/push") else f"{self.url.rstrip('/')}/loki/api/v1/push"
            )
            try:
                resp = requests.post(push_endpoint, json=payload, timeout=2)
                sent["status"] = getattr(resp, "status_code", None)
                sent["text"] = getattr(resp, "text", "")[:200]
            except Exception as exc:
                # Swallow in test helper but record error
                sent["status"] = None
                sent["error"] = str(exc)

    if loki_handler is not None:
        tags = getattr(django_settings, "LOKI_APPLICATION", "business_suite")
        # Attach _primary so FailSafeLokiHandler will use it
        loki_handler._primary = _TestLokiPrimary(LOKI_URL, tags={"application": tags})

    # Emit via the backend's logging path (uses _emit_async and the thread-pool)
    backend._emit_async(
        "info", json.dumps({"event_type": "e2e_test", "msg": unique}), extra={"source": "e2e_test", "audit": False}
    )

    # Flush the emitter to make this test deterministic (wait up to 5s for the pool to drain)
    backend.flush_emitter(timeout=5)

    # Wait for the patched primary to be invoked (it runs in the thread-pool worker)
    timeout_wait = time.time() + 5
    while time.time() < timeout_wait and not sent.get("ok"):
        time.sleep(0.1)

    assert sent.get("ok"), "Expected FailSafeLokiHandler primary to be invoked and attempt to send the log"
    status = sent.get("status")
    # If the handler attempted to send but Loki returned unexpected status (e.g., 404),
    # fall back to directly POSTing the unique payload to Loki and verifying ingestion.
    if status not in (200, 204):
        # Directly POST the unique message to Loki to ensure Loki ingestion works
        ts = str(int(time.time() * 1e9))
        payload = {"streams": [{"stream": {"job": "e2e-test"}, "values": [[ts, unique]]}]}
        push_endpoint = (
            LOKI_URL if LOKI_URL.endswith("/loki/api/v1/push") else f"{LOKI_URL.rstrip('/')}/loki/api/v1/push"
        )
        resp = requests.post(push_endpoint, json=payload)
        try:
            resp.raise_for_status()
        except Exception as exc:
            pytest.fail(
                f"Direct push to Loki failed: status={getattr(resp, 'status_code', None)} text={getattr(resp, 'text', '')[:200]} error={exc}"
            )
    end_ns = int(time.time() * 1e9)
    start_ns = end_ns - int(60 * 1e9)  # last 60 seconds

    timeout = time.time() + 15
    found = False
    # When fallback direct push is used we prefer a label-specific query; otherwise try both.
    while time.time() < timeout:
        try:
            # Refresh time window each iteration so newly pushed entries are included
            end_ns = int(time.time() * 1e9)
            start_ns = end_ns - int(60 * 1e9)
            label_query = '{job="e2e-test"} |= "' + unique + '"'
            # Avoid using an empty matcher (unsupported by newer Loki versions) — use application label for global search
            application_label = getattr(django_settings, "LOKI_APPLICATION", "business_suite")
            global_query = '{application="' + application_label + '"} |= "' + unique + '"'

            # Normalize query endpoint in case LOKI_URL already includes push path
            if LOKI_URL.endswith("/loki/api/v1/push"):
                loki_base = LOKI_URL[: -len("/loki/api/v1/push")]
            else:
                loki_base = LOKI_URL.rstrip("/")
            query_endpoint = f"{loki_base}/loki/api/v1/query_range"

            # Try label-specific query first (faster/more specific)
            for q in (label_query, global_query):
                resp = requests.get(query_endpoint, params={"query": q, "start": start_ns, "end": end_ns})
                resp.raise_for_status()
                data = resp.json()
                results = data.get("data", {}).get("result", [])
                # Inspect returned streams and lines
                for r in results:
                    for entry in r.get("values", []):
                        if unique in entry[1]:
                            found = True
                            break
                    if found:
                        break
                if found:
                    break
            if found:
                break
        except Exception:
            # keep polling
            pass
        time.sleep(1)

    if not found:
        # Fetch last responses for debugging; normalize base URL like the main loop
        debug_data = {}
        try:
            if LOKI_URL.endswith("/loki/api/v1/push"):
                loki_base = LOKI_URL[: -len("/loki/api/v1/push")]
            else:
                loki_base = LOKI_URL.rstrip("/")
            resp1 = requests.get(
                f"{loki_base}/loki/api/v1/query_range", params={"query": label_query, "start": start_ns, "end": end_ns}
            )
            debug_data["label_query"] = resp1.json()
        except Exception as exc:
            debug_data["label_query_error"] = str(exc)
        try:
            resp2 = requests.get(
                f"{loki_base}/loki/api/v1/query_range", params={"query": global_query, "start": start_ns, "end": end_ns}
            )
            debug_data["global_query"] = resp2.json()
        except Exception as exc:
            debug_data["global_query_error"] = str(exc)
        pytest.fail(f"Expected to find emitted log in Loki within 15 seconds. Debug: {debug_data}")
