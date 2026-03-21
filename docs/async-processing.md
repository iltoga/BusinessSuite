# Async Processing

- Framework: Dramatiq 2 with Redis broker/results; tracing middleware `DramatiqTracingMiddleware`.
- Queues: `realtime` (latency-sensitive), `default` (general), `scheduled` (cron), `low` (maintenance), `doc_conversion` (invoice/document rendering).
- Actors:
  - `core/tasks`: ocr, document_ocr, document_validation, document_categorization, calendar_sync, calendar_reminders, cron_jobs, ai_usage, local_resilience, progress, idempotency helpers.
  - `invoices/tasks`: document_jobs, download_jobs, import_jobs.
  - `products/tasks`: product_excel_jobs, price_list_jobs.
  - Additional domain actors in `customer_applications/tasks.py`, `customers/tasks.py`, `admin_tools/tasks.py`.
- Decorators: `@db_task` in `core/tasks/runtime.py` enforces DB context, retry policy (`retry_on_transient_external_failure`), time limits, logging, idempotency.
- Scheduler: `python backend/manage.py run_dramatiq_scheduler` with Redis dedupe key; runs scheduled entries defined in `core/tasks/cron_jobs.py`.
- Workers: `backend/scripts/run_dramatiq_workers.sh` spawns queue-specific process/thread counts; configure via env `DRAMATIQ_*`.
- Results: Redis results backend (namespace `dramatiq:results`, TTL configurable).
- Retries & resilience: Dramatiq retry middleware; idempotency locks around jobs; progress persisted on long-running tasks (OCR jobs, document conversions).
- Monitoring: tracing middleware emits spans; logs include actor, queue, retries; Redis namespaces `dramatiq:queue` and `dramatiq:results`.

## Scheduled Cron Jobs

All scheduled tasks are registered in `core/tasks/cron_jobs.py` and run on the `scheduled` queue via `@db_periodic_task`. Each uses Redis-based enqueue/run locks to prevent concurrent execution.

| Task                  | Default Schedule | Env Variable                                                    | What it does                                                              |
| --------------------- | ---------------- | --------------------------------------------------------------- | ------------------------------------------------------------------------- |
| **Full Backup**       | `02:00` daily    | `FULL_BACKUP_SCHEDULE` (HH:MM)                                  | `dbbackup` + `uploadmediatos3` to S3                                      |
| **Clear Cache**       | `03:00` daily    | `CLEAR_CACHE_SCHEDULE` (HH:MM, supports list)                   | Django `clear_cache` management command                                   |
| **Auditlog Prune**    | `04:00` daily    | `AUDITLOG_RETENTION_SCHEDULE` (HH:MM)                           | `auditlogflush` entries older than `AUDITLOG_RETENTION_DAYS` (default 14) |
| **OpenRouter Health** | Every 5 min      | `OPENROUTER_HEALTHCHECK_CRON_MINUTE` (cron expr, default `*/5`) | GET `/api/v1/key` to verify API key + credit remaining                    |

### Lock Mechanism

Each cron job uses a two-phase Redis lock:

1. **Enqueue lock** — prevents the scheduler from queuing the same task multiple times.
2. **Run lock** — prevents concurrent execution if a previous run hasn't completed.

Lock TTLs: Full Backup = 6 hours (`FULL_BACKUP_LOCK_TTL_SECONDS`), Clear Cache = 15 minutes (`CLEAR_CACHE_LOCK_TTL_SECONDS`).

### On-Demand Execution

Each scheduled task also has an immediate variant callable from APIs/admin:

- `enqueue_full_backup_now()` / `run_full_backup_now()`
- `enqueue_clear_cache_now()` / `run_clear_cache_now()`
- `run_auditlog_prune_now()`
- `run_openrouter_health_check_now()`

### Additional Env Vars

| Variable                                      | Default | Description                                |
| --------------------------------------------- | ------- | ------------------------------------------ |
| `OPENROUTER_HEALTHCHECK_ENABLED`              | `True`  | Master toggle for OpenRouter health checks |
| `OPENROUTER_HEALTHCHECK_TIMEOUT`              | `10.0`  | HTTP timeout for health check requests     |
| `OPENROUTER_HEALTHCHECK_MIN_CREDIT_REMAINING` | `0.0`   | Minimum credit to consider healthy         |
| `AUDITLOG_RETENTION_DAYS`                     | `14`    | Days to retain audit log entries           |
