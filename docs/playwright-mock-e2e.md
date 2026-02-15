# Playwright E2E with Prism Mock Server

This guide describes how to run Playwright against the frontend mock stack (`Prism + Angular`).

## Overview

- Mock API is served from `backend/schema.yaml` using Prism.
- Frontend runs with mock configuration via `frontend` script `dev:mock`.
- Playwright targets `http://localhost:4200`.

## Prerequisites

- Bun installed
- Frontend dependencies installed (`cd frontend && bun install`)
- Backend schema up to date:

```bash
python backend/manage.py generate_frontend_schema
cd frontend && bun run generate:api
```

## Run locally

1. Start mock environment:

```bash
cd frontend
bun run dev:mock
```

This starts:
- Prism on `4010`
- Angular dev server on `4200`

2. In a second terminal, run tests:

```bash
cd frontend
bun run test:e2e
```

## Recommended Playwright config

```ts
import { defineConfig } from '@playwright/test';

export default defineConfig({
  use: {
    baseURL: 'http://localhost:4200',
  },
  webServer: {
    command: 'bun run dev:mock',
    port: 4200,
    reuseExistingServer: process.env.CI ? false : true,
    timeout: 120_000,
  },
});
```

## Tips

- Prefer contract-driven mocks in `backend/schema.yaml` over heavy per-test stubbing.
- Use `page.route()` only for test-specific overrides.
- If response shapes drift, regenerate schema + client before debugging tests.

## CI checklist

```bash
python backend/manage.py generate_frontend_schema
cd frontend && bun run generate:api
cd frontend && bun run test:e2e
```

Set `CI=true` to avoid reusing existing servers.

## Troubleshooting

- Port conflict (`4010`/`4200`):

```bash
lsof -i :4010 -i :4200 -t | xargs kill -9 || true
```

- Prism validation mismatch: regenerate schema and verify endpoint examples/security in schema generation hooks.
- Missing auth behavior in mock mode: verify `/api/app-config/` mock settings are present in generated schema.
