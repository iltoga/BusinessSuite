# Observability setup (Loki + Grafana)

## Dependencies

Backend (uv):

- Add packages:

  uv add django-easy-audit opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-http opentelemetry-instrumentation-django

Frontend (bun):

- Add Faro SDK:

  cd frontend && bun add @grafana/faro-web-sdk

## Run observability stack locally

Start only the observability stack (Loki, Grafana, Grafana Agent) using the local compose file:

```bash
docker-compose -f docker-compose-local.yml up -d loki grafana grafana-agent
```

Grafana will be available at `http://localhost:3000` (default admin/admin or set `GRAFANA_ADMIN_PASSWORD` env var).

## Grafana queries

- Frontend errors: `{app="django", source="angular_frontend"}`
- Backend CRUD events: `{app="django", source="audit"}`

## Notes

- The frontend sends logs to `/api/v1/observability/log/` and the Django proxy logs them using the `angular_frontend` logger.
- The backend `PersistentOTLPBackend` writes `CRUDEvent`, `LoginEvent`, `RequestEvent` to the DB and logs structured JSON to the `audit` logger via OpenTelemetry OTLP.

## Migrations

The audit models were added to `core.models.audit`. After installing dependencies and activating your virtualenv, create and apply migrations:

```bash
python manage.py makemigrations core
python manage.py migrate
```

This will create the `CRUDEvent`, `LoginEvent`, and `RequestEvent` tables required by the persistent audit backend.
