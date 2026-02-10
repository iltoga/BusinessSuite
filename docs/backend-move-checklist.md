# Backend Move Checklist ✅

This checklist helps you validate the repository after moving all Django code into `backend/`.

---

## Pre-move (safety) ⚠️

- [ ] Ensure a clean git working tree:
  - git status --porcelain | wc -l
- [ ] Create a branch: `git checkout -b feature/django-refactor-dir-structure`
- [ ] Run a full grep for repo-root references to fix after the move:
  - git ls-files | xargs grep -nE "context: \./|source: \./|COPY \. \.|\bmanage.py\b" || true

---

## Move steps (suggested) 🔧

Execute these commands from the repo root to move Django components and related files:

```bash
mkdir -p backend/

# Apps & Core modules
x git mv admin_tools/ api/ business_suite/ core/ customer_applications/ backend/
x git mv customers/ invoices/ landing/ letters/ payments/ products/ reports/ backend/

# Project files
x git mv manage.py pyproject.toml uv.lock requirements.txt requirements/ backend/
x git mv fixtures/ locale/ static/ backend/
x git mv schema.yaml schema_dump.yaml backend/ 2>/dev/null || true

# Scripts & Runner
git mv start.sh scripts/ backend/
```

- Commit the move: `git commit -m "Move Django core and related scripts into backend/"`

---

## Automated replacements (refined) 🧰

- The script `scripts/relocate_replace.sh` (now at `backend/scripts/relocate_replace.sh` after the move) updates:
  - `context: ./` -> `context: ./backend/` (Only for `bs-core`)
  - `source: ./` -> `source: ./backend` (Only for app root volume mapping)
  - `COPY . .` -> `COPY backend/ .` in `Dockerfile`
  - `COPY pyproject.toml ...` -> `COPY backend/pyproject.toml ...` in `Dockerfile`
  - `../schema.yaml` -> `../backend/schema.yaml` in `frontend/package.json`
  - Dependency regex in `.github/workflows/deploy.yml`

- Usage:
  - After moving files: `bash backend/scripts/relocate_replace.sh`
  - Apply: `bash backend/scripts/relocate_replace.sh --apply`

---

## Post-move validations ✅

Run these checks and mark each as done when verified:

1. Docker build & compose
   - [ ] Build bs-core & bs-worker with local compose:
     - docker-compose -f docker-compose-local.yml build bs-core bs-worker
   - [ ] Start services and ensure healthy:
     - docker-compose -f docker-compose-local.yml up -d bs-core bs-worker
   - [ ] Verify container has the project in the expected path:
     - docker exec -it bs-core ls /usr/src/app

2. Dockerfile & build context
   - [ ] Confirm `Dockerfile` now copies `backend/` or that `build.context` points to `./backend/`
   - [ ] Check for `COPY . .` elsewhere and fix if needed:
     - git ls-files | xargs grep -n "COPY \. \." || true

3. Compose volume mounts and paths
   - [ ] Ensure `source: ./backend` appears where needed in `docker-compose*.yml`
   - [ ] Confirm `MEDIA_ROOT` / `STATIC_ROOT` mount points are still correct and volumes map to host paths

4. Local helper scripts & manage.py
   - [ ] `scripts/*.sh` that reference `manage.py` were updated to `backend/manage.py`
   - [ ] Run example script(s) like `./scripts/init_db.sh` (with a test DB) to ensure they run

5. Django & tests
   - [ ] From `backend/` run:
     - python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
     - python manage.py check
     - python manage.py test
   - [ ] Run `python manage.py makemigrations` and `migrate` in a dev DB; ensure migrations discover apps

6. CI / GitHub workflows
   - [ ] Update workflow `working-directory` or commands that used repo root paths (tests, coverage uploads, build steps)
   - [ ] Run workflow locally (act) or verify the changes in a PR run

7. Frontend & API generation
   - [ ] If `bun run generate:api` or similar references serializer output or file paths, ensure generated clients are still written and imported correctly
   - [ ] Run `bun run generate:api` in `frontend/` and ensure it succeeds

8. Static/media & storage
   - [ ] Run `python manage.py collectstatic --noinput` (or in Docker) and verify `STATIC_ROOT` contents
   - [ ] Verify media uploads work end-to-end (create a test upload)

9. Worker tasks
   - [ ] Run the worker command from compose or container: `python manage.py run_huey` and verify it starts without error

10. Search & update remaining hardcoded references
    - [ ] Grep for remaining repo-root references:
      - git ls-files | xargs grep -nE "(^|[/: ])(\.|\./)" || true
    - [ ] Check docs and HOWTOs for examples referencing top-level context and update if you changed them

11. Code & import integrity
    - [ ] Run linter (flake8/ruff) and fix any import path issues
    - [ ] Run tests and ensure test coverage remains acceptable

---

## Rollback plan

- If problems appear after the move, revert with:
  - git reset --hard HEAD~1
  - Or use your branch to re-apply fixes iteratively

---

## Notes / Tips 💡

- If you prefer fewer edits inside the repo, another approach is to keep `build.context: ./` and instead change `Dockerfile` to `COPY backend/ /usr/src/app/` so you don't need to update every `docker-compose` file.
- Keep `businesssuite` package name the same to avoid changing `DJANGO_SETTINGS_MODULE` imports.
- Update documentation (README, HOWTOs) to reflect new layout.

---

If you'd like, I can now generate the exact sequence of `git mv` commands and run them (keeping each move in individual commits) and then run `./scripts/relocate_replace.sh --apply` for you. Reply with **yes** to proceed or tell me which step you'd like automated next.
