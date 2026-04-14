#!/usr/bin/env bash
set -euo pipefail

echo "=== filter ==="
tt filter

echo "=== rank ==="
tt rank

echo "=== fetch ==="
tt fetch

echo "=== match ==="
tt match

echo "=== html ==="
tt html

echo "=== report ==="
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
tt report --readme "$SCRIPT_DIR/README.md"

echo "=== git sync ==="
cd "$SCRIPT_DIR"
git add -A
if ! git diff --cached --quiet; then
    git commit -m "Update promise tracker from pipeline run"
    git push
else
    echo "No changes to commit"
fi

echo "=== done ==="
