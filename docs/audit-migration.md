# Audit models removed — migration notes

We replaced the project's legacy local audit models (`CRUDEvent`, `LoginEvent`, `RequestEvent`) with a single, canonical auditing solution using `django-auditlog`.

Why:

- `django-auditlog` provides robust model-change auditing and stores `LogEntry` objects as the canonical persistent records.
- Keeping duplicate DB tables for audit events was confusing and unnecessary.

What changed:

- Legacy models removed: `core/models/audit.py` was deleted (replaced with a deprecation note).
- `core/migrations/0011_remove_audit_models.py` removes the old DB tables.
- `core/audit_handlers.py` now emits structured audit logs only (no DB writes).
- `core/signals.py` forwards `auditlog.models.LogEntry` objects to Loki for observability.
- Tests under `core/tests/test_audit_logging.py` were updated to assert structured logging behavior rather than DB persistence.

Migration steps for deploy:

1. Ensure `django-auditlog` is installed and in `INSTALLED_APPS` (this project includes it by default).
2. Run migrations:

   ```bash
   python manage.py migrate core
   ```

   This will drop the legacy audit tables. Back up DB if you need the historical rows.

3. Verify that `auditlog` is registered for the models you want audited (see `core/apps.py` and `LOGGING_MODE`).
4. Validate that LogEntry creation events appear in Loki/Grafana via the project's forwarding.

## Forwarding controls & tagging

You can control and filter what gets forwarded to Loki and how it is tagged:

- Forwarding to Loki has been removed from the application. Audit events are persisted to the DB by `django-auditlog`; use Grafana Alloy or other tooling to query `auditlog.LogEntry` rows if you need observability.
- Tagging convention:
  - Audit LogEntry events are emitted with `extra={"source": "auditlog", "audit": True}` so they can be filtered in Grafana/Loki (e.g. by `source="auditlog"` or `audit=true`, depending on your label mapping).
  - Other structured audit events (CRUD/login/request emitted by the backend) use `extra={"source": "audit", "audit": False}` so they are distinguishable from LogEntry forwards.
- Forwarding: log emission to Loki is performed synchronously in a small, robust emitter that writes structured JSON lines to `logs/audit.log` and emits via the `audit` logger. Failures to write the file or emit are logged at DEBUG level and do not raise exceptions to the caller.

If you relied on persistent login/request records in the DB: you will need to implement explicit models and storage for those events if you require them beyond what `auditlog.LogEntry` provides.

If you want, I can prepare a PR that includes a short changelog and a README note linking to this doc.
