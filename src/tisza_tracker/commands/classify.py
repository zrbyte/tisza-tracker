"""Classify command: run LLM verdict classification on matched promise-article pairs.

For each unclassified (or stale-prompt) link in ``promise_article_links``:

1. Resolve the article's title, summary, and full_text from whichever DB has
   it (article_text.db preferred; otherwise papers.db or
   matched_entries_history.db).
2. Run the two-pass :class:`~.processors.llm_classifier.LLMClassifier`.
3. Upsert the result into ``llm_classifications``.

After all candidates are classified, run the roll-up: update
``promises.current_status`` based on aggregated verdict counts per promise.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ..core.config import ConfigManager
from ..core.database import DatabaseManager
from ..core.promise_store import PromiseStore
from ..processors.llm_classifier import LLMClassifier

logger = logging.getLogger(__name__)


def _resolve_article(
    db: DatabaseManager,
    entry_id: str,
) -> Optional[Tuple[str, str, Optional[str]]]:
    """Return (title, summary, full_text) for an article entry_id, or None.

    Prefers article_text.db (full_text present), falls back to papers.db
    (title + summary only), then matched_entries_history.db.
    """
    row = db.get_article_text(entry_id)
    if row and (row.get("title") or row.get("summary") or row.get("full_text")):
        return (
            row.get("title") or "",
            row.get("summary") or "",
            row.get("full_text"),
        )

    with db.get_connection("current", row_factory=True) as conn:
        r = conn.execute(
            "SELECT title, summary FROM entries WHERE id = ?", (entry_id,)
        ).fetchone()
        if r:
            return (r["title"] or "", r["summary"] or "", None)

    with db.get_connection("history", row_factory=True) as conn:
        r = conn.execute(
            "SELECT title, summary FROM matched_entries WHERE entry_id = ?",
            (entry_id,),
        ).fetchone()
        if r:
            return (r["title"] or "", r["summary"] or "", None)

    return None


def _load_llm_config(config: Dict[str, Any]) -> Dict[str, Any]:
    cfg = dict(config.get("llm_classification") or {})
    cfg.setdefault("enabled", False)
    return cfg


def _rollup_status(
    verdicts: Dict[str, int],
    rollup_cfg: Dict[str, Any],
    classifications: list[Dict[str, Any]],
) -> Optional[str]:
    """Decide the new promise status from aggregated verdicts.

    *classifications* is the list of full classification rows for this
    promise (to consult per-verdict confidence).  Returns None if no change
    is implied.
    """
    broken_min = float(rollup_cfg.get("broken_min_confidence", 0.7))
    kept_min_votes = int(rollup_cfg.get("kept_min_votes", 2))
    kept_min_conf = float(rollup_cfg.get("kept_min_confidence", 0.6))
    inprog_min_conf = float(rollup_cfg.get("in_progress_min_confidence", 0.5))

    # Pull confidences per verdict
    by_verdict: Dict[str, list[float]] = {"kept": [], "broken": [], "in_progress": []}
    for row in classifications:
        v = row.get("verdict")
        if v in by_verdict:
            by_verdict[v].append(float(row.get("confidence") or 0.0))

    # broken wins if any high-confidence broken vote
    if any(c >= broken_min for c in by_verdict["broken"]):
        return "broken"

    # kept if enough high-confidence kept votes
    kept_strong = [c for c in by_verdict["kept"] if c >= kept_min_conf]
    if len(kept_strong) >= kept_min_votes:
        return "kept"

    # in_progress if any confident in_progress or kept vote
    if any(c >= inprog_min_conf for c in by_verdict["in_progress"]):
        return "in_progress"
    if any(c >= inprog_min_conf for c in by_verdict["kept"]):
        return "in_progress"

    return None  # no change


def run(
    config_path: str,
    *,
    force: bool = False,
    limit: Optional[int] = None,
    promise_id_filter: Optional[str] = None,
    skip_rollup: bool = False,
) -> Dict[str, Any]:
    """Run LLM classification over unclassified promise-article links."""
    cm = ConfigManager(config_path)
    config = cm.load_config()
    llm_cfg = _load_llm_config(config)

    if not llm_cfg.get("enabled"):
        logger.info("llm_classification.enabled is false — skipping")
        return {"classified": 0, "skipped_disabled": True}

    db = DatabaseManager(config)
    ps = PromiseStore(config)

    prompt_version = str(llm_cfg.get("prompt_version") or "v1")
    max_per_promise = llm_cfg.get("max_candidates_per_promise")

    if force:
        # Treat every existing link as unclassified by using a sentinel version
        links = ps.list_unclassified_links("__force__", max_per_promise=max_per_promise)
    else:
        links = ps.list_unclassified_links(prompt_version, max_per_promise=max_per_promise)

    if promise_id_filter:
        links = [l for l in links if l["promise_id"] == promise_id_filter]

    if limit is not None:
        links = links[:limit]

    if not links:
        logger.info("No links require classification (prompt_version=%s)", prompt_version)
        _maybe_rollup(ps, llm_cfg, skip_rollup)
        return {"classified": 0, "total_candidates": 0}

    secrets_dir = Path(cm.base_dir) / "secrets"
    classifier = LLMClassifier(llm_cfg, secrets_dir=secrets_dir)

    classified = 0
    errors = 0
    irrelevant = 0
    for link in links:
        pid = link["promise_id"]
        eid = link["article_entry_id"]

        promise = ps.get_promise(pid)
        if not promise:
            logger.warning("Promise %s vanished; skipping link %s", pid, eid)
            continue

        resolved = _resolve_article(db, eid)
        if not resolved:
            logger.warning("Could not resolve article %s; skipping", eid)
            continue
        title, summary, full_text = resolved

        logger.info("Classifying %s ↔ %s (score=%.2f)", pid, eid[:8], link["relevance_score"])
        result = classifier.classify(
            promise_text=promise["text"],
            article_title=title,
            article_summary=summary,
            article_full_text=full_text,
        )

        ps.upsert_classification(
            promise_id=pid,
            article_entry_id=eid,
            verdict=result["verdict"],
            confidence=result["confidence"],
            evidence_quote=result["evidence_quote"],
            reasoning=result["reasoning"],
            model=result["model"],
            prompt_version=result["prompt_version"],
            pass1_relevant=result["pass1_relevant"],
            pass1_confidence=result["pass1_confidence"],
            error=result["error"],
        )
        if result["error"]:
            errors += 1
        elif result["verdict"] == "irrelevant":
            irrelevant += 1
        classified += 1

    db.close_all_connections()

    summary_msg = (
        f"Classified {classified} links "
        f"(irrelevant={irrelevant}, errors={errors})"
    )
    logger.info(summary_msg)

    _maybe_rollup(ps, llm_cfg, skip_rollup)

    return {
        "classified": classified,
        "errors": errors,
        "irrelevant": irrelevant,
        "total_candidates": len(links),
    }


def _maybe_rollup(ps: PromiseStore, llm_cfg: Dict[str, Any], skip: bool) -> None:
    rollup_cfg = llm_cfg.get("rollup") or {}
    if skip or not rollup_cfg.get("enabled", True):
        return

    # For each promise with at least one classification, recompute status
    with ps._connection() as conn:
        rows = conn.execute("""
            SELECT promise_id FROM llm_classifications
            WHERE verdict IS NOT NULL AND verdict != 'irrelevant'
            GROUP BY promise_id
        """).fetchall()
        promise_ids = [r["promise_id"] for r in rows]

    updated = 0
    for pid in promise_ids:
        verdict_counts = ps.get_verdict_counts(pid)
        with ps._connection() as conn:
            classifications = [dict(r) for r in conn.execute(
                "SELECT verdict, confidence FROM llm_classifications "
                "WHERE promise_id = ? AND verdict IS NOT NULL",
                (pid,),
            ).fetchall()]

        new_status = _rollup_status(verdict_counts, rollup_cfg, classifications)
        if not new_status:
            continue

        current = ps.get_promise(pid)
        if not current:
            continue
        if current["current_status"] == new_status:
            continue

        try:
            ps.update_status(
                pid, new_status,
                evidence=f"llm-rollup: {verdict_counts}",
            )
            updated += 1
        except ValueError as exc:
            logger.warning("Rollup: could not update %s: %s", pid, exc)

    if updated:
        logger.info("Rollup updated %d promise statuses", updated)
