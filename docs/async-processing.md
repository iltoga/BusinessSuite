# Async Processing

- Framework: Dramatiq 2 with Redis broker/results; tracing middleware `DramatiqTracingMiddleware`.
- Queues: `realtime` (latency-sensitive), `default` (general), `scheduled` (cron), `low` (maintenance), `doc_conversion` (invoice/document rendering).
- Actors:
  - `core/tasks`: ocr, document_validation, document_categorization, calendar_sync, calendar_reminders, cron_jobs, ai_usage, local_resilience, idempotency helpers.
  - `invoices/tasks`: document_jobs, download_jobs, import_jobs.
  - `products/tasks`: product_excel_jobs.
  - Additional domain actors in `customer_applications`, `customers`, `admin_tools`.
- Decorators: `@db_task` in `core/tasks/runtime.py` enforces DB context, retry policy (`retry_on_transient_external_failure`), time limits, logging, idempotency.
- Scheduler: `python backend/manage.py run_dramatiq_scheduler` with Redis dedupe key; runs scheduled entries defined in `core/tasks/cron_jobs.py`.
- Workers: `backend/scripts/run_dramatiq_workers.sh` spawns queue-specific process/thread counts; configure via env `DRAMATIQ_*`.
- Results: Redis results backend (namespace `dramatiq:results`, TTL configurable).
- Retries & resilience: Dramatiq retry middleware; idempotency locks around jobs; progress persisted on long-running tasks (OCR jobs, document conversions).
- Monitoring: tracing middleware emits spans; logs include actor, queue, retries; Redis namespaces `dramatiq:queue` and `dramatiq:results`.
