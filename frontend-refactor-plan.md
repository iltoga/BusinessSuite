Use this memory file [](file:///Users/stefano.galassi/Library/Application%20Support/Code%20-%20Insiders/User/workspaceStorage/2bb398a56d8b1bce987ba26bd6cd88e0/GitHub.copilot-chat/memory-tool/memories/Njg1MzQwOTQtNWFkMi00ZmM4LWEzNWEtODNlMWMzOTlkOThl/plan.md)

---

## Plan: Angular 21 Codebase Compliance Audit

**TL;DR**: The codebase is **modern and well-architected** — Angular 21 with zoneless change detection, 100% standalone components, signals-first state management, SSR + hydration, and strong security patterns. The audit surfaces 4 critical issues (legacy template syntax, subscription leaks, excessive `any`, missing security headers), several important improvements (no `@defer`, monolithic components, no ESLint), and a clear modernization path. Estimated maturity: **modern with legacy pockets (~80% migrated)**.

---

### 1. Overall Assessment

| Area                         | Grade  | Notes                                                                                              |
| ---------------------------- | ------ | -------------------------------------------------------------------------------------------------- |
| Architecture & Core Patterns | **A-** | Fully standalone, zoneless, signals-first. Legacy `*ngIf`/`*ngFor` remains in ~50 files            |
| State Management             | **A**  | Zero BehaviorSubject, zero NgRx. Pure signals + computed + rxResource                              |
| Performance                  | **B+** | 100% OnPush, zoneless, but almost no `@defer` and 8 `track $index` usages                          |
| Security                     | **A-** | All innerHTML sanitized, in-memory JWT, HttpOnly cookies. Missing HTTP security headers in Express |
| Code Quality & Standards     | **B**  | Strict TS enabled but 200+ `any` usages, no ESLint config                                          |
| Forms, Routing & Async       | **A-** | Reactive forms with server error mapping, keyboard shortcuts. Some bare subscriptions              |
| Accessibility                | **A-** | Axe E2E scanning, ARIA attrs, keyboard nav. Could add more semantic landmarks                      |
| Error Handling & Resilience  | **A**  | Global + local error handling, toast notifications, circuit-breaker SSE                            |
| Testing & Quality Gates      | **B+** | 63 unit + 8 E2E tests. No ESLint CI gate. Good Vitest/Playwright setup                             |

---

### 2. Critical Issues (Must Fix)

**Issue 1: ~50+ files still import `CommonModule` with legacy structural directives**

- **Problem**: Files like reports.component.ts, customer-list.component.ts, invoice-list.component.ts, and 47+ others import `CommonModule` and use `*ngIf`/`*ngFor` instead of `@if`/`@for`
- **Why it matters**: `CommonModule` is unnecessary overhead in standalone components using built-in control flow. Legacy directives prevent tree-shaking of the `CommonModule` directive set and are deprecated for new Angular code
- **Fix**: Run `ng generate @angular/core:control-flow-migration` to auto-migrate `*ngIf` → `@if`, `*ngFor` → `@for`, `*ngSwitch` → `@switch`. Then remove `CommonModule` from each component's `imports` array. The tsconfig already suppresses `unusedStandaloneImports` — re-enable it after migration to catch future regressions

**Issue 2: ~90+ bare `.subscribe()` calls without lifecycle cleanup**

- **Problem**: Services like reminder-inbox.service.ts (5 bare subscribes), help.service.ts (2), feature components like application-list.component.ts (4), and holidays.component.ts (6) use `.subscribe()` without `takeUntilDestroyed`, `DestroyRef`, or manual unsubscribe
- **Why it matters**: Memory leaks. Subscriptions outlive component/service lifecycle, causing stale callbacks, duplicate side effects, and potential performance degradation over time
- **Fix**: Inject `DestroyRef` in each component/service and pipe `takeUntilDestroyed(this.destroyRef)` before every `.subscribe()`. The base classes already inject `DestroyRef` — subclasses should use `this.destroyRef` directly. For one-shot HTTP calls that complete (like single API fetches), `takeUntilDestroyed` is still recommended as a safety net

**Issue 3: 200+ `any` type usages outside generated code**

- **Problem**: Files like customers.service.ts (4 instances in mappers), cache.service.ts (3), logger.service.ts (6), handle-error.operator.ts (5), and backups.component.ts (4) use `: any` or `as any` extensively
- **Why it matters**: Defeats `strict: true`. `any` silently disables type checking, hiding bugs and making refactoring unsafe. The codebase already has good `unknown` usage (100+ instances in utilities) — the `any` cases are inconsistencies
- **Fix**: Replace `: any` with `: unknown` + type guard narrowing. The codebase's type-guards.ts already provides utilities (`isRecord`, `isString`, etc.). For mapper functions in services, define proper DTOs or use `Record<string, unknown>`

**Issue 4: Express SSR server missing critical HTTP security headers**

- **Problem**: server.ts generates CSP nonces but never sets the `Content-Security-Policy` HTTP header. Also missing: `X-Frame-Options`, `X-Content-Type-Options`, `Strict-Transport-Security`, `Referrer-Policy`
- **Why it matters**: Without these headers, the app is vulnerable to clickjacking (no X-Frame-Options), MIME-type sniffing attacks, and inline script injection. The CSP nonce infrastructure is built but unused
- **Fix**: Add Express middleware before the static file handler that sets all security headers. If a reverse proxy (nginx/Cloudflare) handles these in production, add them as defense-in-depth. At minimum, set `Content-Security-Policy` using the already-generated nonce

---

### 3. Important Improvements

**3a. Almost no `@defer` blocks (only 2 in entire codebase)**

- Currently used only in data-table.component.html and customer-detail.component.html for action menu triggers
- High-value candidates: Chart.js sections in reports.component.html, document preview panels in application-detail, PDF viewer in pdf-viewer-host, admin diagnostics in server-management

**3b. Monolithic components exceeding 500 lines**

- application-detail.component.ts (~1000+ lines) — handles documents, OCR, categorization, workflow timeline, status management
- application-form.component.ts (~500+ lines) — multi-step form with document adapters
- server-management.component.ts (~500+ lines) — AI workflow, diagnostics, repair
- Extract sub-components for each logical section (e.g., `application-documents-panel`, `application-ocr-section`, `application-status-workflow`)

**3c. No ESLint configuration**

- Files contain `eslint-disable` comments but no `.eslintrc` or `eslint.config.js` exists in frontend
- This means no automated lint gate in CI. Add `@angular-eslint/schematics` + `@typescript-eslint/eslint-plugin` with rules for `no-explicit-any`, `no-unused-vars`, and Angular-specific checks

**3d. 8 instances of `track $index` in `@for` loops**

- Found in data-table.component.html, calendar-navigation.component.html, backups.component.html, application-form-documents-section.component.html, and others
- `track $index` causes full re-render when list order changes. Acceptable for: skeleton rows, static UI lists. Should use stable keys for: FormArray controls, dynamic data lists

---

### 4. Minor Issues / Code Smells

1. **`unusedStandaloneImports` suppressed** in tsconfig.json `extendedDiagnostics.checks` — re-enable after CommonModule removal to catch dead imports
2. **`form!: FormGroup` non-null assertion** in base-form.component.ts — could use `declare form: FormGroup` or lazy init pattern
3. **Mixed legacy/modern template syntax in same files** — e.g., customer-list.component.html uses both `*ngIf` and `@if` in the same template
4. **`document.execCommand('copy')`** in reminders.component.ts — deprecated API, should migrate to `navigator.clipboard.writeText()`
5. **`(item as any).id ?? index`** in data-table.component.ts trackBy — could constrain `T extends { id: unknown }` or accept a track key function

---

### 5. Refactoring Plan (Prioritized)

**Phase 1: Security & Stability** _(parallel steps, independently verifiable)_

| Step | Task                                                           | Files                                            | Depends On            |
| ---- | -------------------------------------------------------------- | ------------------------------------------------ | --------------------- |
| 1    | Add security headers middleware to Express SSR server          | server.ts                                        | —                     |
| 2    | Wire CSP header generation using existing nonce infrastructure | server.ts, csp.ts                                | Step 1                |
| 3    | Add `takeUntilDestroyed` to all bare `.subscribe()` calls      | ~50 files across services and feature components | — _(parallel with 1)_ |

**Phase 2: Typing & Code Quality** _(after Phase 1)_

| Step | Task                                                        | Files                                                                               | Depends On            |
| ---- | ----------------------------------------------------------- | ----------------------------------------------------------------------------------- | --------------------- |
| 4    | Set up ESLint with `@angular-eslint` + `@typescript-eslint` | New `eslint.config.js`, `package.json`                                              | —                     |
| 5    | Replace `any` with `unknown` + type guards in core services | customers.service.ts, cache.service.ts, logger.service.ts, handle-error.operator.ts | Step 4                |
| 6    | Extract sub-components from monolithic components           | application-detail.component.ts, server-management.component.ts                     | — _(parallel with 5)_ |

**Phase 3: Template Modernization** _(after Phase 2)_

| Step | Task                                                          | Files                                                  | Depends On |
| ---- | ------------------------------------------------------------- | ------------------------------------------------------ | ---------- |
| 7    | Run `ng generate @angular/core:control-flow-migration`        | ~50+ template files                                    | —          |
| 8    | Remove `CommonModule` imports from all standalone components  | ~50+ component .ts files                               | Step 7     |
| 9    | Re-enable `unusedStandaloneImports` diagnostic in tsconfig    | tsconfig.json                                          | Step 8     |
| 10   | Replace `track $index` with stable keys where data is dynamic | 4-5 template files (FormArray controls, dynamic lists) | Step 7     |

**Phase 4: Performance & Polish** _(after Phase 3)_

| Step | Task                                                            | Files                                                                                     | Depends On             |
| ---- | --------------------------------------------------------------- | ----------------------------------------------------------------------------------------- | ---------------------- |
| 11   | Add `@defer` blocks for charts, document previews, admin panels | reports.component.html, application-detail.component.html, pdf-viewer-host.component.html | —                      |
| 12   | Expand SSR `renderMode: RenderMode.Server` for dashboard        | app.routes.server.ts                                                                      | — _(parallel with 11)_ |
| 13   | Replace `document.execCommand('copy')` with Clipboard API       | reminders.component.ts                                                                    | —                      |

---

### 6. Modernization Opportunities

| Feature                        | Current State                                       | Opportunity                                                                                                  |
| ------------------------------ | --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| **Signals**                    | Extensively used (200+ instances)                   | Already adopted. Continue replacing remaining `any` callback patterns with typed signal flows                |
| **`@if` / `@for` / `@switch`** | ~60% migrated                                       | Complete migration of remaining 50+ files still using `*ngIf`/`*ngFor` via Angular CLI schematic             |
| **SSR + Hydration**            | Enabled but minimal (only `/login` server-rendered) | Expand `RenderMode.Server` to `/dashboard` and public-facing pages for faster FCP                            |
| **`@defer`**                   | 2 instances only                                    | Add for: Chart.js reports, document preview panels, PDF viewer, admin diagnostics                            |
| **`linkedSignal()`**           | 4 instances                                         | Adopt in more places where inputs need local writability (replaces `effect()` + `signal()` two-step pattern) |
| **`rxResource()`**             | Used in BaseListComponent                           | Already well-adopted for list screens; could extend to detail screens for consistent data loading patterns   |
| **Zoneless**                   | Enabled via `provideZonelessChangeDetection()`      | Already fully committed — the most modern Angular setup possible                                             |

---

### 7. Example Refactors

**Example 1: Bare subscription → takeUntilDestroyed** (reminder-inbox.service.ts)

_Before:_

```typescript
// reminder-inbox.service.ts line ~72
this.realtimeService.jobUpdates$.subscribe((event) => {
  this.handleRealtimeEvent(event);
});
```

_After:_

```typescript
private destroyRef = inject(DestroyRef);

// In constructor or init
this.realtimeService.jobUpdates$.pipe(
  takeUntilDestroyed(this.destroyRef)
).subscribe(event => {
  this.handleRealtimeEvent(event);
});
```

---

**Example 2: Legacy template → Modern control flow** (customer-list.component.html)

_Before:_

```html
<div *ngIf="statusFilter() !== 'all'" class="filter-badge">
  Active filter: {{ statusFilter() }}
</div>
<tr *ngFor="let row of items(); trackBy: trackById">
  <td>{{ row.name }}</td>
</tr>
```

_After:_

```html
@if (statusFilter() !== 'all') {
<div class="filter-badge">Active filter: {{ statusFilter() }}</div>
} @for (row of items(); track row.id) {
<tr>
  <td>{{ row.name }}</td>
</tr>
}
```

Then remove `CommonModule` from the component's `imports` array.

---

**Example 3: `any` → `unknown` with type guard** (handle-error.operator.ts)

_Before:_

```typescript
export function handleError<T>(
  toast: GlobalToastService,
  defaultMessage = "Operation failed",
  options?: HandleErrorOptions,
): (source: any) => any {
  return catchError((error: any) => {
    const message =
      extractServerErrorMessage(error) || options?.message || defaultMessage;
    // ...
    const returnValue = options?.returnValue ?? null;
    return of(returnValue);
  });
}
```

_After:_

```typescript
export function handleError<T>(
  toast: GlobalToastService,
  defaultMessage = "Operation failed",
  options?: HandleErrorOptions<T>,
): MonoTypeOperatorFunction<T> {
  return catchError((error: unknown) => {
    const message =
      extractServerErrorMessage(error) || options?.message || defaultMessage;
    // ...
    const returnValue = options?.returnValue ?? (null as T);
    return of(returnValue);
  });
}
```

---

### Verification

1. **Run existing tests**: `cd frontend && bun run test:unit` — all 63 spec files should pass
2. **Run E2E tests**: `cd frontend && bun run test:e2e` — verify accessibility scans still pass
3. **Build check**: `cd frontend && bun run build` — verify no regressions in production build
4. **Manual validation**: After security headers middleware, inspect response headers with `curl -I http://localhost:4200`
5. **After CommonModule removal**: Run `ng build` and grep for remaining `CommonModule` imports — count should be 0 (excluding generated API module)

### Decisions

- ESLint setup should use flat config (`eslint.config.js`) since Angular 21 supports it
- CSP in report-only mode initially, enforce after validation
- SSR expansion limited to pages that benefit from SEO/FCP (dashboard, login) — not admin pages
- Monolithic component split is a separate task from template migration to avoid merge conflicts

### Further Considerations

1. **Add pre-commit hooks** (e.g., via `husky` + `lint-staged`) to enforce ESLint + Prettier before commits — prevents new `any` and legacy syntax from entering the codebase
2. **Consider Angular Signals-based forms** (`signal-based forms` RFC) when available in stable — the current `ReactiveFormsModule` approach is correct for now but the ecosystem is moving toward signal forms
3. **Route-level lazy loading for admin features** — the admin sub-routes already use `loadChildren` but heavy feature components (reports with Chart.js) could benefit from `@defer` + `@loading`/`@placeholder` blocks to reduce initial bundle

4. **After CommonModule removal**: Run `ng build` and grep for remaining `CommonModule` imports — count should be 0 (excluding generated API module)

### Decisions

- ESLint setup should use flat config (`eslint.config.js`) since Angular 21 supports it
- CSP in report-only mode initially, enforce after validation
- SSR expansion limited to pages that benefit from SEO/FCP (dashboard, login) — not admin pages
- Monolithic component split is a separate task from template migration to avoid merge conflicts

### Further Considerations

1. **Add pre-commit hooks** (e.g., via `husky` + `lint-staged`) to enforce ESLint + Prettier before commits — prevents new `any` and legacy syntax from entering the codebase
2. **Consider Angular Signals-based forms** (`signal-based forms` RFC) when available in stable — the current `ReactiveFormsModule` approach is correct for now but the ecosystem is moving toward signal forms
3. **Route-level lazy loading for admin features** — the admin sub-routes already use `loadChildren` but heavy feature components (reports with Chart.js) could benefit from `@defer` + `@loading`/`@placeholder` blocks to reduce initial bundle
