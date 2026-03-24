#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v bun >/dev/null 2>&1; then
  echo "[update-bun] bun is not available on PATH. Install Bun first."
  exit 1
fi

usage() {
  cat <<'EOF'
Usage: scripts/update-bun-dependencies.sh [options] [target-dir ...]

Update Bun-managed dependencies in one or more package.json directories.

Defaults to:
  - frontend
  - desktop

Options:
  -l, --latest         Ignore semver ranges and upgrade to the absolute latest versions.
  -n, --dry-run        Show what would happen without changing files.
  -p, --production     Skip devDependencies.
      --lockfile-only  Update the lockfile only; do not install packages.
      --frozen-lockfile Fail if the lockfile would change.
      --ignore-scripts Skip package lifecycle scripts.
      --no-save        Do not write package.json changes.
      --verbose        Enable verbose Bun output.
      --omit <types>   Omit dependency types (for example: dev,optional,peer).
  -h, --help          Show this help text.

Examples:
  scripts/update-bun-dependencies.sh
  scripts/update-bun-dependencies.sh frontend
  scripts/update-bun-dependencies.sh --dry-run --verbose
  scripts/update-bun-dependencies.sh --latest desktop
  scripts/update-bun-dependencies.sh --production --omit dev frontend
EOF
}

LATEST=0
DRY_RUN=0
PRODUCTION=0
LOCKFILE_ONLY=0
FROZEN_LOCKFILE=0
IGNORE_SCRIPTS=0
NO_SAVE=0
VERBOSE=0
OMIT_VALUE=""
TARGETS=()

while (($#)); do
  case "$1" in
    -l|--latest)
      LATEST=1
      ;;
    -n|--dry-run)
      DRY_RUN=1
      ;;
    -p|--production)
      PRODUCTION=1
      ;;
    --lockfile-only)
      LOCKFILE_ONLY=1
      ;;
    --frozen-lockfile)
      FROZEN_LOCKFILE=1
      ;;
    --ignore-scripts)
      IGNORE_SCRIPTS=1
      ;;
    --no-save)
      NO_SAVE=1
      ;;
    --verbose)
      VERBOSE=1
      ;;
    --omit)
      shift
      if [[ $# -eq 0 ]]; then
        echo "[update-bun] --omit requires a value (for example: dev or dev,optional)."
        exit 1
      fi
      OMIT_VALUE="$1"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      while (($#)); do
        TARGETS+=("$1")
        shift
      done
      break
      ;;
    -*)
      echo "[update-bun] Unknown option: $1"
      usage
      exit 1
      ;;
    *)
      TARGETS+=("$1")
      ;;
  esac
  shift
done

if ((${#TARGETS[@]} == 0)); then
  TARGETS=(frontend desktop)
fi

BUN_ARGS=()
if [[ "$LATEST" -eq 1 ]]; then
  BUN_ARGS+=(--latest)
fi
if [[ "$DRY_RUN" -eq 1 ]]; then
  BUN_ARGS+=(--dry-run)
fi
if [[ "$PRODUCTION" -eq 1 ]]; then
  BUN_ARGS+=(--production)
fi
if [[ "$LOCKFILE_ONLY" -eq 1 ]]; then
  BUN_ARGS+=(--lockfile-only)
fi
if [[ "$FROZEN_LOCKFILE" -eq 1 ]]; then
  BUN_ARGS+=(--frozen-lockfile)
fi
if [[ "$IGNORE_SCRIPTS" -eq 1 ]]; then
  BUN_ARGS+=(--ignore-scripts)
fi
if [[ "$NO_SAVE" -eq 1 ]]; then
  BUN_ARGS+=(--no-save)
fi
if [[ "$VERBOSE" -eq 1 ]]; then
  BUN_ARGS+=(--verbose)
fi
if [[ -n "$OMIT_VALUE" ]]; then
  BUN_ARGS+=(--omit "$OMIT_VALUE")
fi

echo "[update-bun] Root: $ROOT_DIR"
echo "[update-bun] Targets: ${TARGETS[*]}"
if [[ "$LATEST" -eq 1 ]]; then
  echo "[update-bun] Mode: latest versions (ignoring semver ranges)"
else
  echo "[update-bun] Mode: latest compatible versions (respecting semver ranges)"
fi
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[update-bun] Dry run enabled; no files will be changed."
fi

for target in "${TARGETS[@]}"; do
  target_dir="$ROOT_DIR/$target"
  package_json="$target_dir/package.json"

  if [[ ! -d "$target_dir" ]]; then
    echo "[update-bun] Skipping missing directory: $target"
    continue
  fi
  if [[ ! -f "$package_json" ]]; then
    echo "[update-bun] Skipping $target_dir (no package.json found)."
    continue
  fi

  echo "[update-bun] Updating $target_dir"
  bun update --cwd "$target_dir" "${BUN_ARGS[@]}"
done

echo "[update-bun] Done."