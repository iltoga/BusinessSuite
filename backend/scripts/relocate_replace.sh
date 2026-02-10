#!/usr/bin/env bash
set -euo pipefail

# relocate_replace.sh
# macOS-safe sed script to update common repo-root references when moving Django code
# into a new `backend/` subdirectory.
# Usage:
#   ./scripts/relocate_replace.sh        # dry-run (shows matches)
#   ./scripts/relocate_replace.sh --apply  # perform replacements (requires clean git tree)

DRY_RUN=1
if [[ "${1:-}" == "--apply" ]]; then
  DRY_RUN=0
fi

# Ensure git working tree is clean if applying
if [[ $DRY_RUN -eq 0 ]]; then
  if [[ -n "$(git status --porcelain)" ]]; then
    echo "Error: Working tree is not clean. Commit or stash changes before running with --apply."
    exit 1
  fi
fi

# Search patterns (files are restricted to tracked files via git ls-files)
PATTERN="context: \./|source: \./|COPY \. \.|\bmanage.py\b"

echo "Searching for matches (dry-run mode: $([[ $DRY_RUN -eq 1 ]] && echo yes || echo no))"

grep -nE "$PATTERN" $(git ls-files) || true

if [[ $DRY_RUN -eq 1 ]]; then
  echo "\nDry-run complete. Re-run with --apply to make changes."
  exit 0
fi

# --- Apply replacements (macOS sed: use -i '' for in-place edits) ---

# 1) docker-compose: Only update context/source for bs-core and bs-worker app root
# We use a pattern that matches the specific volume mapping for /usr/src/app
for f in docker-compose.yml docker-compose-local.yml; do
  if [[ -f "$f" ]]; then
    echo "Updating app volume sources in $f"
    # Match lines where source is ./ and target is /usr/src/app (multi-line awareness via context)
    # Since sed is line-based, we target 'source: ./' only in sections where 'target: /usr/src/app' follows.
    # More safely, we target the specific build context for backend-related services.

    # Update build context for bs-core (appears after container_name: bs-core)
    sed -i '' '/bs-core:/,/context: \.\// s|context: \.\/|context: ./backend/|' "$f"

    # Update volume source for bs-core and bs-worker ROOT mapping
    # We look for the exact pair of source: ./ and target: /usr/src/app
    sed -i '' 's|source: \.\/$|source: ./backend|g' "$f"
    sed -i '' 's|target: /usr/src/app$|target: /usr/src/app|g' "$f" # noop for clarity
  fi
done

# 2) Dockerfile: precise updates for pyproject/uv.lock and root copy
if [[ -f Dockerfile ]]; then
  echo "Updating Dockerfile paths"
  sed -i '' 's|COPY pyproject.toml uv.lock ./|COPY backend/pyproject.toml backend/uv.lock ./|g' Dockerfile
  sed -i '' 's|COPY \. \.|COPY backend/ .|g' Dockerfile
  sed -i '' 's|/usr/src/app/scripts|/usr/src/app/scripts|g' Dockerfile # remains same as backend/scripts -> /usr/src/app/scripts
fi

# 3) Frontend scripts: schema.yaml path
if [[ -f frontend/package.json ]]; then
  echo "Updating frontend schema paths"
  sed -i '' 's|\.\./schema\.yaml|../backend/schema.yaml|g' frontend/package.json
fi

# 4) Workflows: dependency change detection
if [[ -f .github/workflows/deploy.yml ]]; then
  echo "Updating deploy workflow dependency regex"
  sed -i '' "s|'(pyproject\\\\.toml|'(backend/pyproject\\\\.toml|g" .github/workflows/deploy.yml
  sed -i '' "s|requirements\\\\.txt|backend/requirements\\\\.txt|g" .github/workflows/deploy.yml
  sed -i '' "s|locale/|backend/locale/|g" .github/workflows/deploy.yml
fi

# 4) Helpful confirmation: show resulting diffs
echo "\nReplacements applied. Showing git status and diffs (if any):"

git --no-pager status --porcelain

git --no-pager --no-color diff --name-only || true

echo "\nDone. Review changes, run tests, and commit when satisfied."
