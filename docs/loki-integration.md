# Loki Integration

Status: direct in-app Loki pushes are deprecated in this codebase.

Current approach:
- Application logs are written to stdout/stderr and local `logs/` files.
- Log shipping is handled by external collectors (for example Grafana Alloy).
- Audit events are persisted via `django-auditlog` and can be exported/indexed externally.

## What changed in the refactor

- The project no longer treats `python-logging-loki` direct push as the primary path.
- Observability should rely on container/file scraping and centralized collection.
- Keep application logging focused on structured, useful messages; let infrastructure handle forwarding.

## Recommended setup

1. Ensure backend logs are available to your collector:
   - container stdout/stderr
   - mounted `logs/` directory if file scraping is enabled
2. Configure Alloy/Promtail/agent to label streams by service (`backend`, `worker`, `frontend`).
3. In Grafana/Loki, build queries/dashboards on those labels.

## Local checks

- Verify logs are emitted:
  - backend startup logs
  - API request/error logs
  - PgQueuer worker task logs
- Verify collector can read the configured sources.

## If you need direct push again

Reintroduce a dedicated handler in settings/logger service and document:
- env vars
- handler wiring
- rollout and fallback behavior

Do not re-enable ad hoc in multiple modules.
