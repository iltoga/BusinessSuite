"""
Django management command to run AI passport parser tests across models/files.
Writes results and metrics into the tmp/ directory.

Usage: python manage.py run_ai_passport_tests

Options:
  --models MODEL [MODEL ...]    Space-separated list of models to test
  --files FILE [FILE ...]       Space-separated list of files to test
  --use-openrouter              Force using OpenRouter (default True)
  --output DIR                  Output directory under tmp/ (defaults to tmp/ai_passport_results)

"""

from __future__ import annotations

import json
import os
import time
from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand

from core.services.ai_client import AIClient
from core.services.ai_passport_parser import AIPassportParser

DEFAULT_MODELS = [
    # "qwen/qwen2.5-vl-32b-instruct",
    "google/gemma-3-12b-it",
    "google/gemini-2.5-flash-lite",
    # "google/gemini-2.0-flash-lite-001",
    "mistralai/mistral-small-3.2-24b-instruct",
]

DEFAULT_FILES = [
    # Only include the single file by default. Add more as needed.
    "tmp/passport.jpeg",
    "tmp/passport_1.jpg",
    "tmp/passport_2.jpeg",
    "tmp/passport_3.jpeg",
]


class Command(BaseCommand):
    help = "Run AI passport parser tests across multiple models and files and write metrics to tmp/."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--models",
            nargs="*",
            default=DEFAULT_MODELS,
            help="List of models to test (space separated)",
        )
        parser.add_argument(
            "--files",
            nargs="*",
            default=DEFAULT_FILES,
            help="List of files to test (space separated)",
        )
        parser.add_argument(
            "--use-openrouter",
            action="store_true",
            default=True,
            help="Force using OpenRouter (default True)",
        )
        parser.add_argument(
            "--output",
            default="tmp/ai_passport_results",
            help="Output directory where metrics will be written",
        )

    def handle(self, *args: Any, **options: Any) -> None:  # pragma: no cover - manual test
        models = options.get("models") or DEFAULT_MODELS
        files = options.get("files") or DEFAULT_FILES
        use_openrouter = bool(options.get("use_openrouter"))
        output_dir = Path(options.get("output") or "tmp/ai_passport_results")
        output_dir.mkdir(parents=True, exist_ok=True)

        results = []

        # Loop over the models and files
        for model in models:
            self.stdout.write(self.style.NOTICE(f"Testing model: {model}"))
            try:
                parser = AIPassportParser(model=model, use_openrouter=use_openrouter)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to initialize parser for model {model}: {e}"))
                continue

            ai_client = parser.ai_client
            # For deeper metrics we'll call the underlying client directly
            client = ai_client.client

            for file_path in files:
                file_path_obj = Path(file_path)
                if not file_path_obj.exists():
                    self.stdout.write(self.style.WARNING(f"File {file_path} not found, skipping."))
                    continue

                # Read bytes
                file_bytes, detected_filename = AIClient.read_file_bytes(file_path_obj.read_bytes())
                filename = detected_filename or file_path_obj.name

                messages = ai_client.build_vision_message(
                    prompt=parser._build_vision_prompt(),
                    image_bytes=file_bytes,
                    filename=filename,
                    system_prompt=parser.SYSTEM_PROMPT,
                )

                json_schema = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "passport_data",
                        "strict": True,
                        "schema": parser.PASSPORT_SCHEMA,
                    },
                }

                # Prepare request kwargs similar to AIClient.chat_completion_json
                request_kwargs = {
                    "model": ai_client.model,
                    "messages": messages,
                    "temperature": 0.1,
                    "response_format": json_schema,
                }

                self.stdout.write(self.style.NOTICE(f"Calling API for file {file_path} with model {model}"))

                start_ts = time.monotonic()
                start_dt = datetime.utcnow().isoformat() + "Z"
                try:
                    response = client.chat.completions.create(**request_kwargs)
                except Exception as e:  # pragma: no cover - external API call
                    self.stdout.write(self.style.ERROR(f"Model call failed for {model} / {file_path}: {e}"))
                    results.append(
                        {
                            "model": model,
                            "file": file_path,
                            "error": str(e),
                        }
                    )
                    continue

                end_ts = time.monotonic()
                end_dt = datetime.utcnow().isoformat() + "Z"
                elapsed = end_ts - start_ts

                # Extract usage if available
                usage = getattr(response, "usage", None)
                prompt_tokens = None
                completion_tokens = None
                total_tokens = None
                if usage is not None:
                    if hasattr(usage, "prompt_tokens"):
                        prompt_tokens = usage.prompt_tokens
                    elif isinstance(usage, dict) and "prompt_tokens" in usage:
                        prompt_tokens = usage.get("prompt_tokens")

                    if hasattr(usage, "completion_tokens"):
                        completion_tokens = usage.completion_tokens
                    elif isinstance(usage, dict) and "completion_tokens" in usage:
                        completion_tokens = usage.get("completion_tokens")

                    if hasattr(usage, "total_tokens"):
                        total_tokens = usage.total_tokens
                    elif isinstance(usage, dict) and "total_tokens" in usage:
                        total_tokens = usage.get("total_tokens")

                # Extract text content
                content = None
                try:
                    content = response.choices[0].message.content
                except Exception:
                    try:
                        content = response.choices[0].message["content"]
                    except Exception:
                        # as fallback, string
                        content = str(response)

                # Parse response JSON
                parsed_data = None
                try:
                    parsed_data = json.loads(content)
                except Exception:
                    # Some providers may return an already-parsed object
                    parsed_data = content

                # Attempt to collect confidence score
                confidence = None
                if isinstance(parsed_data, dict):
                    confidence = parsed_data.get("confidence_score")

                # Build a field:value list
                fields_list = []
                if isinstance(parsed_data, dict):
                    for k, v in parsed_data.items():
                        fields_list.append(f"{k}: {v}")

                # Compose result
                run_result = {
                    "model": model,
                    "file": file_path,
                    "model_provider": ai_client.provider_name,
                    "model_name": ai_client.model,
                    "start_time": start_dt,
                    "end_time": end_dt,
                    "elapsed_seconds": elapsed,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "confidence_score": confidence,
                    "fields": parsed_data,
                    "raw_response": str(response),
                }

                # Save per-run file
                out_name = f"ai_passport_{model.replace('/', '_')}_{file_path_obj.name}.json"
                out_path = output_dir / out_name
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(run_result, f, ensure_ascii=False, indent=2)

                self.stdout.write(self.style.SUCCESS(f"Saved result: {out_path}"))
                results.append(run_result)

        # Write summary comparison table
        comp_path = output_dir / "ai_passport_comparison.txt"
        self._write_summary(results, comp_path)
        self.stdout.write(self.style.SUCCESS(f"Comparison table saved to: {comp_path}"))

    def _write_summary(self, results: list[dict], out_path: Path) -> None:
        """Write a simple tabular summary of results."""
        headers = [
            "model",
            "file",
            "provider",
            "model_name",
            "elapsed_seconds",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "confidence_score",
            "passport_number",
            "expiration_date",
            "first_name",
            "last_name",
        ]

        lines = ["\t".join(headers)]

        for r in results:
            if r.get("error"):
                row = [r.get("model"), r.get("file"), "ERROR", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-"]
            else:
                fields = r.get("fields") or {}
                passport_number = fields.get("passport_number") if isinstance(fields, dict) else "-"
                expiration_date = fields.get("passport_expiration_date") if isinstance(fields, dict) else "-"
                first_name = fields.get("first_name") if isinstance(fields, dict) else "-"
                last_name = fields.get("last_name") if isinstance(fields, dict) else "-"

                row = [
                    r.get("model"),
                    r.get("file"),
                    r.get("model_provider"),
                    r.get("model_name"),
                    f"{r.get('elapsed_seconds', '-'):.2f}" if r.get("elapsed_seconds") else "-",
                    str(r.get("prompt_tokens") or "-"),
                    str(r.get("completion_tokens") or "-"),
                    str(r.get("total_tokens") or "-"),
                    str(r.get("confidence_score") or "-"),
                    str(passport_number or "-"),
                    str(expiration_date or "-"),
                    str(first_name or "-"),
                    str(last_name or "-"),
                ]

            lines.append("\t".join(row))

        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    # Backward compatibility for running as script via manage.py run_ai_passport_tests
