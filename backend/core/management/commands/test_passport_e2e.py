"""
E2E passport check test. Uses threading.Timer + os._exit() for a HARD
process kill that cannot be blocked by httpx or any other I/O.

Usage:
  python manage.py test_passport_e2e
  python manage.py test_passport_e2e --model qwen/qwen3.5-flash-02-23
  python manage.py test_passport_e2e --timeout 30
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from argparse import ArgumentParser
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand

from core.services.ai_client import AIClient
from core.services.ai_passport_parser import AIPassportParser


def _hard_kill(timeout_s: int) -> None:
    """Force-kill the process. Called from a daemon thread."""
    sys.stderr.write(f"\n*** HARD TIMEOUT after {timeout_s}s — killing process ***\n")
    sys.stderr.flush()
    os._exit(99)


class Command(BaseCommand):
    help = "E2E test: parse a passport image via chat_completion_json with a hard timeout."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--model",
            default="google/gemini-3-flash-preview",
            help="Model to test (default: google/gemini-3-flash-preview)",
        )
        parser.add_argument(
            "--file",
            default="tmp/passport_1.jpg",
            help="Passport image file (default: tmp/passport_1.jpg)",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=30,
            help="Hard timeout in seconds (default: 30)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        from django.conf import settings

        model = options["model"]
        # Resolve file path relative to project root (parent of BASE_DIR / backend)
        project_root = Path(settings.BASE_DIR).parent
        raw_path = Path(options["file"])
        file_path = raw_path if raw_path.is_absolute() else project_root / raw_path
        timeout_s = options["timeout"]

        if not file_path.exists():
            self.stderr.write(self.style.ERROR(f"File not found: {file_path}"))
            return

        # Start the hard-kill timer (daemon thread, cannot be blocked)
        kill_timer = threading.Timer(timeout_s, _hard_kill, args=[timeout_s])
        kill_timer.daemon = True
        kill_timer.start()

        self.stdout.write(self.style.NOTICE(f"Model:   {model}"))
        self.stdout.write(self.style.NOTICE(f"File:    {file_path}"))
        self.stdout.write(self.style.NOTICE(f"Timeout: {timeout_s}s (hard kill)"))
        self.stdout.write("")

        try:
            self._run_test(model, file_path, timeout_s)
        except Exception as exc:
            import traceback
            self.stderr.write(self.style.ERROR(f"EXCEPTION: {exc}"))
            traceback.print_exc()
        finally:
            kill_timer.cancel()

    def _run_test(self, model: str, file_path: Path, timeout_s: int) -> None:
        self.stdout.write("  [1/5] Initializing parser...")
        # Use a client-level timeout that's shorter than the hard kill
        client_timeout = max(timeout_s - 5, 10)
        parser = AIPassportParser(model=model, use_openrouter=True)
        # Override the client timeout to match our test timeout
        parser.ai_client.client = parser.ai_client.client.with_options(timeout=client_timeout)
        parser.ai_client.timeout = client_timeout
        self.stdout.write(f"  Provider: {parser.ai_client.provider_name}")
        self.stdout.write(f"  Model:    {parser.ai_client.model}")
        self.stdout.write(f"  Client timeout: {client_timeout}s")

        self.stdout.write("  [2/5] Reading image...")
        image_bytes = file_path.read_bytes()
        file_bytes, detected = AIClient.read_file_bytes(image_bytes)
        filename = detected or file_path.name
        self.stdout.write(f"  Image size: {len(file_bytes)} bytes")

        self.stdout.write("  [3/5] Building messages...")
        prompt = parser._build_vision_prompt()
        messages = parser.ai_client.build_vision_message(
            prompt=prompt,
            image_bytes=file_bytes,
            filename=filename,
            system_prompt=parser.SYSTEM_PROMPT,
        )
        self.stdout.write(f"  Messages: {len(messages)} items")

        self.stdout.write("  [4/5] Calling chat_completion_json (REAL code path)...")
        t0 = time.monotonic()
        result = parser.ai_client.chat_completion_json(
            messages=messages,
            json_schema=parser.PASSPORT_SCHEMA,
            schema_name="passport_data",
        )
        elapsed = time.monotonic() - t0

        self.stdout.write("  [5/5] Parsing results...")
        self.stdout.write(self.style.SUCCESS(f"  Completed in {elapsed:.1f}s"))
        self.stdout.write(f"  passport_number: {result.get('passport_number')}")
        self.stdout.write(f"  first_name:      {result.get('first_name')}")
        self.stdout.write(f"  last_name:       {result.get('last_name')}")
        self.stdout.write(f"  confidence:      {result.get('confidence_score')}")
        self.stdout.write(self.style.SUCCESS("  RESULT: PASS"))
