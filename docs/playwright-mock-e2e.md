# Playwright E2E Tests with the Mock Server (Prism)

This document explains how to write and run Playwright end-to-end tests against the local mock server (Stoplight Prism) used by the BusinessSuite frontend.

## ✅ Overview

- Run the frontend in `mock` configuration using `bun run dev:mock` (starts Prism and `ng serve` configured to use the mock backend).
- Tests should use Playwright's `baseURL` and `webServer` fixtures when possible so tests can start/stop the server automatically in CI.
- The mock server serves routes from the generated `schema.yaml`. Update the OpenAPI schema and regenerate the client if API contracts change (`python manage.py generate_frontend_schema` → `cd frontend && bun run generate:api`).

---

## Prerequisites

- Bun installed (project uses Bun for scripts)
- Playwright installed (dev dependency in `frontend/package.json`)
- The project schema regenerated when API changes are made:

```bash
# In project root
./.venv/bin/python manage.py generate_frontend_schema
# In frontend
cd frontend && bun run generate:api
```

---

## Local development: run mock + tests manually

1. Start the mock dev environment:

```bash
cd frontend
bun run dev:mock
```

This fires up Prism on port `4010` and the Angular dev server on `4200` (see the `dev:mock` npm script). If Prism fails with `EADDRINUSE` it means the port is in use — kill the process and restart:

```bash
lsof -i :4010 -t | xargs kill -9 || true
# or clear both ports
lsof -i :4200 -i :4010 -t | xargs kill -9 || true
```

1. Run Playwright tests in another terminal:

```bash
# From frontend/ or repo root (use package scripts)
cd frontend
bun run test:e2e
# or directly
npx playwright test
```

---

## Recommended Playwright config snippet

Add (or update) your `playwright.config.ts` to start the mock environment automatically when running tests:

```ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  use: {
    baseURL: "http://localhost:4200",
  },
  webServer: {
    command: "bun run dev:mock",
    port: 4200,
    reuseExistingServer: process.env.CI ? false : true,
    timeout: 120_000,
  },
});
```

Notes:

- `webServer` will run `dev:mock` which starts Prism and the dev server in parallel.
- `reuseExistingServer` helps speed up local development by reusing a running server.

---

## Writing tests: examples & tips

- The mock environment sets `MOCK_AUTH_ENABLED` in `/api/app-config/` so the frontend can short-circuit authentication. Verify the schema contains this example or seed `localStorage` if you need custom behavior.

Example test (TypeScript):

```ts
import { test, expect } from "@playwright/test";

test.describe("Dashboard (mock)", () => {
  test.beforeEach(async ({ page }) => {
    // If you need to force auth token before app load
    await page.addInitScript(() => {
      localStorage.setItem("token", "mock-token");
    });
  });

  test("loads dashboard and shows stats", async ({ page }) => {
    await page.goto("/dashboard");

    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible();
    await expect(page.getByText("Total Customers")).toBeVisible();
    await expect(page.getByText(/0|\d+/)).toBeVisible();
  });
});
```

- Use `page.route()` if you need to override a particular response for a single test.
- Prefer to use the mock schema to manage global routes (e.g., `/api/customers/`, `/api/dashboard-stats/`) rather than stubbing too much in tests.

---

## CI recommendations

- Ensure CI jobs regenerate the schema when backend changes are present:
  - `python manage.py generate_frontend_schema`
  - `cd frontend && bun run generate:api`
- Use the Playwright `webServer` option to start `bun run dev:mock` as part of the test job.
- Set `CI=true` in environment to make `webServer` start from scratch (no reuse of existing dev servers).

Example CI step (simplified):

```yaml
- name: Run Playwright E2E
  env:
    CI: true
  run: |
    cd frontend
    bun install --production=false
    bun run test:e2e
```

---

## Troubleshooting & common pitfalls

- Port collisions (EADDRINUSE) — use `lsof` to kill processes on `4010` and `4200`.
- Prism validation errors: if Prism responds with 500 or `UNAUTHORIZED` because of missing security definitions, make sure OpenAPI postprocessing (see `core/openapi.py`) includes the example responses for `/api/app-config/` and relaxes strict security on logging endpoints.
- If tests fail due to unexpected response shapes, regenerate the frontend client and re-run tests (`bun run generate:api`).

---

## Further reading

- docs/playwright-mock-e2e.md (this doc)
- `frontend/package.json` scripts: `dev:mock`, `mock:server`, `start:mock`, and `test:e2e`
- `core/openapi.py` — post-processing hooks used to inject infra endpoints
