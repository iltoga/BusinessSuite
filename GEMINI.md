# Gemini Context & Instructions - BusinessSuite

## Project Overview
BusinessSuite is a Django-based ERP/CRM for service agencies, handling visa applications, document processing, invoices, and payments.
**Current Focus:** Migrating the legacy Django Template frontend to a decoupled, modern Angular 19 SPA.

## Core Mandates
- **Role:** Senior Full Stack Developer (Expert in Django & Angular 19).
- **Philosophy:** Adhere to DRY principles, strict typing, and architectural standards.
- **Migration Authority:** STRICTLY follow the specifications in `copilot/specs/django-angular/`.

## Technology Stack

### Backend (Django)
- **Framework:** Django >= 6.0, Django REST Framework (DRF) 3.16+.
- **Database:** PostgreSQL.
- **Authentication:** Token-based (DRF).
- **Testing:** `pytest` (via `uv run`).

### Frontend (Angular)
- **Framework:** Angular 19+ (Standalone Components, Signals).
- **Runtime & PM:** **Bun** (exclusively; no npm/node).
- **UI Library:** ZardUI (Tailwind CSS v4).
- **State Management:** Signals & Computed (NO `BehaviorSubject` / `NgModules`).

## Operational Workflow

### 1. Research & Plan
- **Search First:** Check `docs/shared_components.md` and the codebase for reusable components/services before creating new ones.
- **Consult Specs:** For any frontend work, refer to `copilot/specs/django-angular/` (Design, Requirements, Anti-Patterns).
- **Library Docs:** Use `#context7` for ZardUI, Tailwind v4, and Angular 19 documentation.

### 2. Implementation Guidelines

#### Backend (Django)
- **Business Logic:** Place in `core/services/` or `managers/`. **Keep views thin.**
- **API:** Use DRF `APIView` or `ModelViewSet`. Ensure serializers handle camelCase/snake_case conversion.
- **Database:** Always use `select_related` / `prefetch_related` to prevent N+1 queries.
- **Security:** Never hardcode credentials. Use environment variables.

#### Frontend (Angular)
- **Working Directory:** All frontend commands must be run from the `frontend/` directory.
- **Architecture:** 
  - Use **Standalone Components** only.
  - Enforce `ChangeDetectionStrategy.OnPush`.
  - Use **Signals** for state.
- **Data Layer:** 
  - **NEVER** manually write TypeScript interfaces for API models.
  - Run `bun run generate:api` to sync types from the backend.
- **ZardUI:** Do not edit `components/ui/` directly. Create wrapper components for customizations.

### 3. Verification & Quality Control
- **Static Analysis:** Check the "Problems" panel immediately after coding to fix types/linting errors.
- **Backend Testing:** Run `uv run pytest`.
- **Frontend Testing:** Run `bun test` (ensure you are in `frontend/`).
- **Build Check:** Run `bun run build` to verify production builds.

### 4. Automatic Cleanup
- **Remove:** Unused imports, dead code, `console.log`, and debug statements.
- **Consolidate:** Merge duplicate logic into shared utilities.
- **Document:** Update `docs/shared_components.md` if you create or modify reusable components.

## Command Reference

| Context | Action | Command |
| :--- | :--- | :--- |
| **Backend** | Run Tests | `uv run pytest` |
| **Backend** | Run Script | `source .venv/bin/activate && python ...` |
| **Backend** | Migrations | `python backend/manage.py makemigrations` |
| **Frontend** | Install Deps | `cd frontend && bun install` |
| **Frontend** | Dev Server | `cd frontend && bun run dev` |
| **Frontend** | Sync API Types | `cd frontend && bun run generate:api` |
| **Frontend** | Run Tests | `cd frontend && bun test` |

## Directory Structure
- `backend/`: Django project root (apps, `manage.py`).
- `frontend/`: Angular project root. **(Root for all `bun` commands)**.
- `copilot/specs/django-angular/`: Migration specifications & design docs.
- `docs/`: Project documentation (Shared components, API endpoints).

## Critical Rules
1.  **Frontend Root:** Always verify you are in `frontend/` before running Angular/Bun commands.
2.  **No Manual Types:** If backend models change, update the serializer and run `bun run generate:api`.
3.  **Strict Signals:** Do not use RxJS `BehaviorSubject` for state management in Angular.
4.  **Component Reuse:** Check `docs/shared_components.md` before building UI.
