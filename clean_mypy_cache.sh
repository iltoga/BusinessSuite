#!/usr/bin/env bash
set -euo pipefail

# Remove all .mypy_cache, .pytest_cache and __pycache__ directories from repo root and backend recursively.
# Usage: ./clean_mypy_cache.sh

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Cleaning .mypy_cache, .pytest_cache, __pycache__ under $root ..."
find "$root" -type d \( -name '.mypy_cache' -o -name '.pytest_cache' -o -name '__pycache__' \) -prune -print -exec rm -rf {} +

echo "Done."
