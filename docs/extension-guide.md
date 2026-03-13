# Extension Guide

## Add a Backend Service
- Place new domain logic in existing app `services/` or create a new app if boundary is distinct.
- Define models + migrations; add serializer + viewset/APIView; register route in `api/urls.py`.
- Add permissions/throttles; regenerate OpenAPI (`./refresh-schema-and-api.sh` or `cd backend && python manage.py spectacular --file schema.yaml`), then regenerate the Angular client.
- Add tests (model/service/view); document updates in `docs/architecture.md` or app-specific notes.

## Add a Background Job
- Implement actor with `@db_task` in appropriate `tasks` module; choose queue intentionally.
- Use idempotency helpers for same-entity operations; persist progress for long jobs.
- Wire trigger point in service or signal; add scheduler entry if periodic.
- Document queue choice and retry policy.

## Extend the API
- Update serializer/viewset; keep camelCase outputs; apply proper throttling scope.
- Regenerate schema + Angular client; update frontend services/components.
- Adjust cache namespace versioning when payload shape changes.

## Add an Angular Feature/Module
- Create folder under `features/`; use standalone components; reuse `shared/components`.
- Wire route in `config`; use generated API client; respect cache and auth interceptors.
- Add unit tests + optional Playwright journey; update shared registry if adding reusable UI.

## Maintain Architectural Consistency
- Update `docs/shared_components.md` for new shared UI.
- Keep cache versioning in mind; bust per-user namespace on contract changes.
- Log meaningful events; add waffle flag for risky rollouts.
- Keep DRF schema, client generation, and documentation in sync with code changes.
