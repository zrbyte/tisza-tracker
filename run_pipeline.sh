#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
set +u; [[ -f "$HOME/.profile" ]] && source "$HOME/.profile"; set -u

export PATH="$HOME/.local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"

echo "=== git pull ==="
# `tt` is an editable install of this checkout, so pulling is what puts a pull
# request merged on GitHub into use (a change to this script itself applies
# from the next run).  --rebase also replays a tracker commit that an earlier
# run could not push.  Non-fatal: offline, or if the rebase conflicts, the run
# goes ahead with the code already checked out.
if ! git -C "$SCRIPT_DIR" pull --rebase; then
    git -C "$SCRIPT_DIR" rebase --abort 2>/dev/null || true
    echo "  WARN: git pull failed — continuing with the checked-out code"
fi

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
        echo "  WARN: tt classify failed — continuing with existing evidence"
    fi
fi

if command -v sqlite3 >/dev/null 2>&1 && [[ -f "$PROMISES_DB" ]]; then
    echo "  --- evidence summary ---"
    sqlite3 -column -header "$PROMISES_DB" \
        "SELECT COALESCE(signal, CASE WHEN error IS NOT NULL THEN '(failed)'
                                      ELSE '(not yet extracted)' END) AS signal,
                COUNT(*) AS count
         FROM llm_classifications
         GROUP BY 1
         ORDER BY count DESC;"
    echo "  --- promise status summary ---"
    sqlite3 -column -header "$PROMISES_DB" \
        "SELECT current_status, COUNT(*) AS count
         FROM promises
         GROUP BY current_status
         ORDER BY count DESC;"
fi

echo "=== review ==="
# Reported reversals, lapsed deadlines and single-source delivery reports are
# not published automatically; they are listed here for a human decision.
if ! tt promise review; then
    echo "  WARN: tt promise review failed"
fi

echo "=== report ==="
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
