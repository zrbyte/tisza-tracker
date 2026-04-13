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

echo "=== done ==="
