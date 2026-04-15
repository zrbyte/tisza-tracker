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

echo "=== classify ==="
# Resolve the promises.db path the same way tisza_tracker does: honour
# TISZA_TRACKER_DATA_DIR when set, otherwise fall back to ~/.tisza_tracker.
TT_DATA_DIR="${TISZA_TRACKER_DATA_DIR:-${HOME}/.tisza_tracker}"
PROMISES_DB="${TT_DATA_DIR}/promises.db"

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
    echo "  skipped: OPENAI_API_KEY is not set"
else
    # Non-fatal: an LLM outage should not sink the report stage.
    if ! tt classify; then
        echo "  WARN: tt classify failed — continuing with existing verdicts"
    fi
fi

if command -v sqlite3 >/dev/null 2>&1 && [[ -f "$PROMISES_DB" ]]; then
    echo "  --- verdict summary ---"
    sqlite3 -column -header "$PROMISES_DB" \
        "SELECT verdict, COUNT(*) AS count
         FROM llm_classifications
         WHERE verdict IS NOT NULL
         GROUP BY verdict
         ORDER BY count DESC;"
    echo "  --- promise status summary ---"
    sqlite3 -column -header "$PROMISES_DB" \
        "SELECT current_status, COUNT(*) AS count
         FROM promises
         GROUP BY current_status
         ORDER BY count DESC;"
fi

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
