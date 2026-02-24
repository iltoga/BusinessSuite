"""
Management command to test and benchmark AI document categorization.

Usage:
    python manage.py test_document_categorization [--dir PATH] [--models MODEL1,MODEL2]

Tests categorization against files in testfiles/multi_uploads_ai_categorize/
using specified LLM models and prints benchmarking results.
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from core.services.ai_document_categorizer import AIDocumentCategorizer, get_document_types_for_prompt
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Test and benchmark AI document categorization with multiple models"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dir",
            type=str,
            default=None,
            help="Directory containing test files (default: testfiles/multi_uploads_ai_categorize/)",
        )
        parser.add_argument(
            "--models",
            type=str,
            default="openai/gpt-5-nano,google/gemini-2.5-flash-lite",
            help="Comma-separated list of models to test",
        )
        parser.add_argument(
            "--sequential",
            action="store_true",
            help="Run files sequentially instead of in parallel",
        )

    def handle(self, *args, **options):
        # Determine test directory
        test_dir = options["dir"]
        if not test_dir:
            # BASE_DIR = backend/business_suite, so .parent.parent = project root
            base = Path(settings.BASE_DIR).parent.parent
            test_dir = base / "testfiles" / "multi_uploads_ai_categorize"
        else:
            test_dir = Path(test_dir)

        if not test_dir.exists():
            self.stderr.write(self.style.ERROR(f"Test directory not found: {test_dir}"))
            return

        # Collect test files (skip hidden files)
        test_files = sorted([f for f in test_dir.iterdir() if f.is_file() and not f.name.startswith(".")])

        if not test_files:
            self.stderr.write(self.style.ERROR(f"No test files found in {test_dir}"))
            return

        self.stdout.write(self.style.SUCCESS(f"\n{'='*80}"))
        self.stdout.write(self.style.SUCCESS("AI Document Categorization Benchmark"))
        self.stdout.write(self.style.SUCCESS(f"{'='*80}"))
        self.stdout.write(f"\nTest directory: {test_dir}")
        self.stdout.write(f"Test files ({len(test_files)}):")
        for f in test_files:
            size_kb = f.stat().st_size / 1024
            self.stdout.write(f"  - {f.name} ({size_kb:.1f} KB)")

        # Fetch document types from DB
        document_types = get_document_types_for_prompt()
        if not document_types:
            self.stderr.write(self.style.ERROR("No document types found in database. Run fixtures first."))
            return

        self.stdout.write(f"\nDocument types ({len(document_types)}):")
        for dt in document_types:
            self.stdout.write(f"  - {dt['name']}" + (f": {dt['description']}" if dt.get("description") else ""))

        # Parse models
        models_config = self._parse_models(options["models"])
        sequential = options["sequential"]

        self.stdout.write(f"\nModels to test: {len(models_config)}")
        for mc in models_config:
            provider_info = f" (providers: {mc['provider_order']})" if mc.get("provider_order") else ""
            self.stdout.write(f"  - {mc['model']}{provider_info}")

        # Read all files into memory once
        file_data = []
        for f in test_files:
            file_data.append(
                {
                    "filename": f.name,
                    "bytes": f.read_bytes(),
                    "size_kb": f.stat().st_size / 1024,
                }
            )

        # Run benchmark for each model
        for mc in models_config:
            self._benchmark_model(mc, file_data, document_types, sequential)

        self.stdout.write(self.style.SUCCESS(f"\n{'='*80}"))
        self.stdout.write(self.style.SUCCESS("Benchmark complete!"))

    def _parse_models(self, models_str: str) -> list[dict]:
        """Parse models config string into list of model configs."""
        configs = []
        for model_name in models_str.split(","):
            model_name = model_name.strip()
            if not model_name:
                continue

            config = {"model": model_name, "provider_order": None}

            # Azure-only for gpt-5-nano
            if "gpt-5-nano" in model_name:
                config["provider_order"] = ["azure"]

            configs.append(config)
        return configs

    def _benchmark_model(self, model_config: dict, file_data: list, document_types: list, sequential: bool):
        """Benchmark a single model against all test files."""
        model_name = model_config["model"]
        provider_order = model_config.get("provider_order")

        self.stdout.write(self.style.WARNING(f"\n{'─'*80}"))
        self.stdout.write(self.style.WARNING(f"Model: {model_name}"))
        if provider_order:
            self.stdout.write(self.style.WARNING(f"Provider order: {provider_order}"))
        self.stdout.write(self.style.WARNING(f"{'─'*80}"))

        categorizer = AIDocumentCategorizer(
            model=model_name,
            provider_order=provider_order,
        )

        # Sequential benchmark (per-file timing)
        self.stdout.write(f"\n📊 Sequential results:")
        self.stdout.write(f"{'File':<55} {'Type':<30} {'Conf':>6} {'Time':>8}")
        self.stdout.write(f"{'─'*55} {'─'*30} {'─'*6} {'─'*8}")

        sequential_results = []
        total_sequential_time = 0

        for fd in file_data:
            start = time.perf_counter()
            try:
                result = categorizer.categorize_file(
                    file_bytes=fd["bytes"],
                    filename=fd["filename"],
                    document_types=document_types,
                )
                elapsed = time.perf_counter() - start
                total_sequential_time += elapsed

                doc_type = result.get("document_type") or "❌ NO MATCH"
                confidence = result.get("confidence", 0)
                reasoning = result.get("reasoning", "")

                sequential_results.append(
                    {
                        "filename": fd["filename"],
                        "document_type": result.get("document_type"),
                        "confidence": confidence,
                        "reasoning": reasoning,
                        "time": elapsed,
                        "error": None,
                    }
                )

                # Color code confidence
                conf_str = f"{confidence:.2f}"
                if confidence >= 0.9:
                    conf_display = self.style.SUCCESS(conf_str)
                elif confidence >= 0.7:
                    conf_display = self.style.WARNING(conf_str)
                else:
                    conf_display = self.style.ERROR(conf_str)

                self.stdout.write(f"{fd['filename']:<55} {doc_type:<30} {conf_str:>6} {elapsed:>7.2f}s")

            except Exception as exc:
                elapsed = time.perf_counter() - start
                total_sequential_time += elapsed
                sequential_results.append(
                    {
                        "filename": fd["filename"],
                        "document_type": None,
                        "confidence": 0,
                        "reasoning": "",
                        "time": elapsed,
                        "error": str(exc),
                    }
                )
                self.stdout.write(self.style.ERROR(f"{fd['filename']:<55} {'ERROR':<30} {'0.00':>6} {elapsed:>7.2f}s"))
                self.stdout.write(self.style.ERROR(f"  └─ {exc}"))

        self.stdout.write(f"{'─'*55} {'─'*30} {'─'*6} {'─'*8}")
        self.stdout.write(f"{'TOTAL (sequential)':<55} {'':<30} {'':>6} {total_sequential_time:>7.2f}s")

        # Parallel benchmark
        if not sequential:
            self.stdout.write(f"\n⚡ Parallel results:")
            parallel_start = time.perf_counter()

            parallel_results = {}
            # Recreate categorizer for fresh client
            par_categorizer = AIDocumentCategorizer(
                model=model_name,
                provider_order=provider_order,
            )

            def _categorize(fd):
                file_start = time.perf_counter()
                try:
                    result = par_categorizer.categorize_file(
                        file_bytes=fd["bytes"],
                        filename=fd["filename"],
                        document_types=document_types,
                    )
                    file_elapsed = time.perf_counter() - file_start
                    return {
                        "filename": fd["filename"],
                        "document_type": result.get("document_type"),
                        "confidence": result.get("confidence", 0),
                        "time": file_elapsed,
                        "error": None,
                    }
                except Exception as exc:
                    file_elapsed = time.perf_counter() - file_start
                    return {
                        "filename": fd["filename"],
                        "document_type": None,
                        "confidence": 0,
                        "time": file_elapsed,
                        "error": str(exc),
                    }

            with ThreadPoolExecutor(max_workers=len(file_data)) as executor:
                futures = {executor.submit(_categorize, fd): fd["filename"] for fd in file_data}
                for future in as_completed(futures):
                    result = future.result()
                    parallel_results[result["filename"]] = result

            parallel_elapsed = time.perf_counter() - parallel_start

            self.stdout.write(f"{'File':<55} {'Type':<30} {'Conf':>6} {'Time':>8}")
            self.stdout.write(f"{'─'*55} {'─'*30} {'─'*6} {'─'*8}")

            for fd in file_data:
                r = parallel_results[fd["filename"]]
                doc_type = r.get("document_type") or "❌ NO MATCH"
                if r.get("error"):
                    doc_type = "ERROR"
                conf = f"{r['confidence']:.2f}"
                self.stdout.write(f"{r['filename']:<55} {doc_type:<30} {conf:>6} {r['time']:>7.2f}s")

            self.stdout.write(f"{'─'*55} {'─'*30} {'─'*6} {'─'*8}")
            self.stdout.write(f"{'TOTAL (parallel, wall clock)':<55} {'':<30} {'':>6} {parallel_elapsed:>7.2f}s")

        # Summary
        success_count = sum(1 for r in sequential_results if r["document_type"] is not None and not r["error"])
        error_count = sum(1 for r in sequential_results if r["error"])
        no_match_count = sum(1 for r in sequential_results if r["document_type"] is None and not r["error"])
        avg_confidence = sum(r["confidence"] for r in sequential_results if r["document_type"]) / max(success_count, 1)
        avg_time = total_sequential_time / len(file_data)

        self.stdout.write(f"\n📋 Summary for {model_name}:")
        self.stdout.write(f"  Files:          {len(file_data)}")
        self.stdout.write(f"  Categorized:    {success_count}")
        self.stdout.write(f"  No match:       {no_match_count}")
        self.stdout.write(f"  Errors:         {error_count}")
        self.stdout.write(f"  Avg confidence: {avg_confidence:.3f}")
        self.stdout.write(f"  Avg time/file:  {avg_time:.2f}s")
        self.stdout.write(f"  Total seq time: {total_sequential_time:.2f}s")
        if not sequential:
            self.stdout.write(f"  Total par time: {parallel_elapsed:.2f}s")
            speedup = total_sequential_time / parallel_elapsed if parallel_elapsed > 0 else 0
            self.stdout.write(f"  Parallel speedup: {speedup:.1f}x")

        # Print reasoning details
        self.stdout.write(f"\n📝 Reasoning details:")
        for r in sequential_results:
            if r.get("error"):
                self.stdout.write(self.style.ERROR(f"  {r['filename']}: ERROR - {r['error']}"))
            else:
                self.stdout.write(f"  {r['filename']}:")
                self.stdout.write(f"    → {r['document_type'] or 'NO MATCH'} ({r['confidence']:.2f})")
                self.stdout.write(f"    {r['reasoning']}")
