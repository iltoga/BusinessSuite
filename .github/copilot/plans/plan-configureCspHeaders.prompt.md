# Plan: Configure CSP headers for Angular SPA

## Summary ✅

- Goal: Implement a robust, nonce-based Content Security Policy for the Angular SPA served via Bun/Node SSR behind nginx, while preserving a clean API behavior for the Django backend at /api/. Start in report-only mode, iterate, and then enforce.

## Constraints & Requirements 🔧

- Angular 20 build served via `dist/business-suite-frontend/server/server.mjs` (Bun/Node SSR).
- nginx acts as gateway/proxy (see `nginx/conf.d/angular.conf`).
- Django API lives under `/api/` and should not be broken by CSP headers for JSON responses.
- Prefer nonce-based approach to allow Angular's dynamically inserted <style> and optional inline critical CSS and to avoid unsafe-\*.
- Use `Content-Security-Policy-Report-Only` initially to collect violations.

## High-level Steps (ordered) 🛠️

1. **SSR: generate per-request nonce and expose it via response header (`X-CSP-Nonce`) and inject it into SSR output**
   - Add secure random nonce generation in server (e.g., crypto.randomBytes(16).toString('base64')).
   - Inject into HTML using `<app ngCspNonce="...">` or `globalThis.__CSP_NONCE__` + Angular `CSP_NONCE` token.

2. **nginx: read upstream nonce header and add CSP header per response**
   - Add a `map $upstream_http_x_csp_nonce $csp_nonce { default "'nonce-$upstream_http_x_csp_nonce'"; "" ""; }` in `http {}`
   - In `location /` add `add_header Content-Security-Policy-Report-Only "... script-src 'self' $csp_nonce; style-src 'self' $csp_nonce; connect-src 'self' https://crm.revisbali.com wss:; img-src 'self' data: blob:; font-src 'self' data:; ..." always;`
   - Use `Report-Only` until stable; then switch to enforcement header.

3. **Django: enable CSP reporting & per-view control**
   - Add `django.middleware.csp.ContentSecurityPolicyMiddleware` to `MIDDLEWARE` (remember django uses pyproject.toml and uv to manage and install dependencies).
   - Configure `SECURE_CSP_REPORT_ONLY` initially and include `script-src` and `style-src` with `CSP.NONCE`.
   - For JSON API endpoints, either decorate with `@csp_override({})` or exclude them from CSP middleware to avoid unexpected headers.

4. **Trusted Types (optional)**
   - Consider adding `require-trusted-types-for 'script'; trusted-types angular;` after validation and browser support checks.

5. **Service worker & WebSockets**
   - Ensure `worker-src` and `connect-src` allow service worker scope and `wss:` for SSE/WS endpoints.

6. **Testing & rollout**
   - Start in `Report-Only` mode and collect violation reports. Fix missing sources, hashes, or nonces.
   - Once stable, flip to enforcement and add Trusted Types if desired.

## Practical trade-offs & mitigations

- **Performance & overhead**: nonce generation is lightweight (microseconds) and network overhead is negligible (small headers). The primary operational cost is **cache impact**: per-request nonces can reduce HTML cache effectiveness and complicate CDN/edge caching unless mitigated.

- **Mitigations**:
  - **Edge injection**: use an edge worker (Cloudflare Worker, Fastly VCL, Lambda@Edge) to inject a per-request nonce into cached HTML at the edge. This preserves cache hit ratios while providing fresh nonces.
  - **CSP_NONCE injection token (runtime injection)**: keep `index.html` cacheable and set a runtime global (or use `CSP_NONCE` injection token) so the cached HTML does not embed a nonce; then the server/edge sets a runtime variable the app consumes.
  - **Hash-based CSP**: for static inline snippets, use SHA-256 hashes instead of per-request nonces to avoid dynamic nonces completely.
  - **Careful cache rules**: avoid `Cache Everything` without edge injection and set explicit `Cache-Control` headers for HTML.
  - **Report-only first**: collect violations, iterate on allowed sources, and only then enforce.
  - **Use strict-dynamic carefully**: it can simplify script allowances but has varying browser support.
  - **Security hardening**: keep `X-Content-Type-Options: nosniff` and other headers in place to avoid MIME-sniffing attacks.

- **Operational checklist**:
  - Verify CDN/proxy rules do not cache per-request nonce values.
  - Monitor CSP report endpoints and browser console errors during rollout.
  - Ensure your logging/CI picks up any cached-nonce incidents.

## Feature flag (enable/disable CSP)

- **Recommendation**: implement the feature flag in the **frontend SSR server** (env vars) rather than Django. Rationale: the SSR server is the generator of nonces and is the natural place to enable/disable or switch CSP modes without cross-service calls or additional complexity.

- **Env variables**:
  - `CSP_ENABLED=true|false` — whether CSP headers/nonces should be emitted.
  - `CSP_MODE=report-only|enforce` — whether to emit `Content-Security-Policy-Report-Only` or `Content-Security-Policy`.

- **Implementation sketch**:

```js
const cspEnabled = process.env.CSP_ENABLED === "true";
const cspMode = process.env.CSP_MODE || "report-only"; // report-only|enforce
if (cspEnabled) {
  res.setHeader("X-CSP-Nonce", nonce);
  res.setHeader("X-CSP-Mode", cspMode);
}
```

- **nginx**: read `$upstream_http_x_csp_nonce` and `$upstream_http_x_csp_mode` and conditionally emit `Content-Security-Policy(-Report-Only)` header. (Use a short if/map in nginx config to switch header name between report-only and enforce.)

- **Optional**: Mirror a control flag in Django (via `SECURE_CSP` / django-waffle) when you need centralized toggling across services; this can be used for administration UI but keep the SSR env var as the immediate runtime control.

## Tests & validation

- **Unit tests** (fast):
  - Nonce generation unit test (Node/Jest): generate 1k nonces => assert uniqueness, base64 format, minimum length (>=16 bytes).

- **Integration tests** (CI / staging):
  - **Header presence test**: set `CSP_ENABLED=true` and assert that an HTTP request to `/` returns a `Content-Security-Policy` or `Content-Security-Policy-Report-Only` header containing a `'nonce-...` token.
  - **Toggle test**: set `CSP_ENABLED=false` and assert that no CSP header is present.
  - **Mode test**: `CSP_MODE=report-only` => header name `Content-Security-Policy-Report-Only`; `CSP_MODE=enforce` => `Content-Security-Policy`.

- **Cache behavior tests**:
  - **No-cache dev test**: with caching off, make two sequential requests to `/` and assert the returned nonce values are different (ensures per-request nonces work).
  - **Cached response simulation**: configure a simple caching proxy (or use `Cache-Control: max-age` plus a test proxy) to return a cached HTML body. Verify that cached responses do not leak the same nonce across users (test fails if a cached nonce is reused). If using edge injection, verify the edge injects a fresh nonce per request.
  - **CDN/Edge test**: if using Cloudflare/Fastly/Varnish, add an automated check in CI that requests a cached URL multiple times from different clients and asserts nonce uniqueness or correct edge injection.

- **Django tests**:
  - Verify API endpoints (`/api/`) are not returning CSP headers (use `@csp_override({})` in critical APIs and add a Django test asserting header absence).

- **CI / automation**:
  - Add a pipeline job that deploys a temporary environment (Docker Compose with nginx + frontend SSR) and runs the integration & cache tests. Use `report-only` mode by default for this job.

---

## Example snippets (for engineers) ✍️

- Server (pseudo):

```js
const nonce = crypto.randomBytes(16).toString("base64");
res.setHeader("X-CSP-Nonce", nonce);
// inject into SSR HTML root: <app ngCspNonce="${nonce}"></app>
```

- nginx map + header (conceptual):

```nginx
map $upstream_http_x_csp_nonce $csp_nonce { default "'nonce-$upstream_http_x_csp_nonce'"; "" ""; }
add_header Content-Security-Policy-Report-Only "default-src 'self'; script-src 'self' $csp_nonce; style-src 'self' $csp_nonce; connect-src 'self' https://crm.revisbali.com wss:; img-src 'self' data: blob:; font-src 'self' data:; object-src 'none';" always;
```

## Docker / Build notes

- No Dockerfile changes required unless you add new runtime dependencies; rebuild frontend image so `dist/server/server.mjs` includes nonce logic.

## Acceptance criteria ✅

- CSP headers present on SPA HTML responses with a valid nonce.
- Angular bootstraps and renders with no CSP violations in production.
- API JSON endpoints are free of CSP enforcement headers or explicitly excluded.
- Report-only violations are low before flipping to enforcement.

## Next tasks (for refinement) ▶️

- Create exact patch for `nginx/conf.d/angular.conf` (add map + header in http/server blocks).
- Add nonce-generation + SSR injection to `dist` server source (example file or middleware).
- Add Django `SECURE_CSP_REPORT_ONLY` and decide API exclusions.

---

_End of plan — ready for refinement._
