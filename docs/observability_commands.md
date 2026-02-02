# Observability dependency installation commands

## Backend (uv)

Run from repository root in your Python environment:

```bash
uv add django-easy-audit opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-http opentelemetry-instrumentation-django

# Remove old Loki-specific library
uv remove python-logging-loki
```

Then update `pyproject.toml` (already added in this branch) and run your typical install flow (e.g., `uv install` or rebuild your environment).

## Frontend (bun)

Run inside the `frontend/` directory:

```bash
cd frontend && bun add @grafana/faro-web-sdk
```

(Alternatively use `bun add ngx-logger` if you prefer the lightweight logger.)
