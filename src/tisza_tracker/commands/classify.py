"""Classify command: run LLM evidence extraction on matched promise-article pairs.

For each link in ``promise_article_links`` that still needs it (new, stale
prompt, or failed on an earlier run):

1. Resolve the article's title, summary, full text, outlet and publication
   date from whichever DBs have them (article_text.db for the text; papers.db,
   matched_entries_history.db and all_feed_entries.db for the rest).
2. Run the two-pass :class:`~.processors.llm_classifier.LLMClassifier`.  An
   article that passes the relevance gate without a stored body has its body
   downloaded first, so no status ever rests on a headline alone.
3. Upsert the result into ``llm_classifications``.

After all candidates are classified, run the roll-up: weigh each promise's
evidence with :func:`~.processors.evidence_ledger.assess` and update
``promises.current_status``.
"""

from __future__ import annotations

import html
import logging
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

from ..core.config import ConfigManager
from ..core.database import DatabaseManager
from ..core.promise_store import DEFAULT_MAX_ATTEMPTS, PromiseStore
from ..processors.article_fetcher import ArticleFetcher, strip_paywall
from ..processors.evidence_ledger import REVIEW_PREFIX, assess, promise_kind
from ..processors.llm_classifier import LLMClassifier, effective_prompt_version

logger = logging.getLogger(__name__)

# Statuses only a person assigns; the rollup never moves a promise out of them.
_MANUAL_ONLY_STATUSES = ("abandoned", "modified")

# Where an article's metadata can be found, in order of preference.
_ARTICLE_SOURCES = (
    ("current",
     "SELECT title, summary, link, feed_name, published_date "
     "FROM entries WHERE id = ?"),
    ("history",
     "SELECT title, summary, link, feed_name, published_date "
     "FROM matched_entries WHERE entry_id = ?"),
    ("all_feeds",
     "SELECT title, summary, link, feed_name, published_date "
     "FROM feed_entries WHERE entry_id = ?"),
)


_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _plain(text: Optional[str]) -> str:
    """RSS titles and teasers as one line of plain text."""
    return _WS.sub(" ", html.unescape(_TAG.sub(" ", text or ""))).strip()


def _col(row: Any, key: str) -> Any:
    try:
        return row[key]
    except (IndexError, KeyError):
        return None


def _resolve_article(
    db: DatabaseManager,
    entry_id: str,
) -> Optional[Dict[str, Any]]:
    """Return what is known about an article entry_id, or None.

    The result has ``title``, ``summary``, ``full_text``, ``url``, ``outlet``
    and ``published``.  Text comes from article_text.db when it has the entry;
    outlet, publication date and anything still missing are filled in from
    papers.db, then matched_entries_history.db, then all_feed_entries.db.
    """
    article: Dict[str, Any] = {
        "title": "", "summary": "", "full_text": None,
        "url": "", "outlet": None, "published": None,
    }
    found = False

    row = db.get_article_text(entry_id)
    if row and (row.get("title") or row.get("summary") or row.get("full_text")):
        found = True
        article["title"] = row.get("title") or ""
        article["summary"] = row.get("summary") or ""
        article["full_text"] = strip_paywall(row.get("full_text")) or None
        article["url"] = row.get("url") or ""

    for db_key, sql in _ARTICLE_SOURCES:
        if found and article["url"] and article["outlet"] and article["published"]:
            break
        with db.get_connection(db_key, row_factory=True) as conn:
            r = conn.execute(sql, (entry_id,)).fetchone()
        if not r:
            continue
        if not found:
            found = True
            article["title"] = _col(r, "title") or ""
            article["summary"] = _col(r, "summary") or ""
        article["url"] = article["url"] or _col(r, "link") or ""
        article["outlet"] = article["outlet"] or _col(r, "feed_name")
        article["published"] = article["published"] or (
            str(_col(r, "published_date") or "")[:10] or None
        )

    if not found:
        return None
    article["title"] = _plain(article["title"])
    article["summary"] = _plain(article["summary"])
    return article


def _fetch_body(
    db: DatabaseManager,
    fetcher: ArticleFetcher,
    entry_id: str,
    article: Dict[str, Any],
) -> Optional[str]:
    """Download an article's body and cache it in article_text.db."""
    url = article.get("url")
    if not url:
        return None
    text, status = fetcher.fetch_text(url)
    db.save_article_text(
        entry_id, url, text,
        fetch_status=status, title=article.get("title"), summary=article.get("summary"),
    )
    if status != "ok":
        logger.warning("Entry %s body fetch '%s': %s", entry_id[:8], status, url)
    return strip_paywall(text) or None


def _load_llm_config(config: Dict[str, Any]) -> Dict[str, Any]:
    cfg = dict(config.get("llm_classification") or {})
    cfg.setdefault("enabled", False)
    return cfg


def _max_attempts(llm_cfg: Dict[str, Any]) -> int:
    return int(llm_cfg.get("max_attempts") or DEFAULT_MAX_ATTEMPTS)


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

    prompt_version = effective_prompt_version(llm_cfg)
    links = ps.list_unclassified_links(
        prompt_version,
        max_per_promise=llm_cfg.get("max_candidates_per_promise"),
        max_attempts=_max_attempts(llm_cfg),
        force=force,
    )

    if promise_id_filter:
        links = [l for l in links if l["promise_id"] == promise_id_filter]

    if limit is not None:
        links = links[:limit]

    if not links:
        logger.info("No links require classification (prompt_version=%s)", prompt_version)
        ps.update_best_articles()
        _maybe_rollup(ps, llm_cfg, skip_rollup)
        return {"classified": 0, "total_candidates": 0}

    secrets_dir = Path(cm.base_dir) / "secrets"
    classifier = LLMClassifier(
        llm_cfg, secrets_dir=secrets_dir, government=config.get("government"),
    )

    classified = 0
    errors = 0
    irrelevant = 0
    with ArticleFetcher() as fetcher:
        for link in links:
            pid = link["promise_id"]
            eid = link["article_entry_id"]

            promise = ps.get_promise(pid)
            if not promise:
                logger.warning("Promise %s vanished; skipping link %s", pid, eid)
                continue

            article = _resolve_article(db, eid)
            if not article:
                # Recorded as a failure so the link is retried a few times
                # and then stops holding up the promise's rollup.
                logger.warning("Could not resolve article %s", eid)
                ps.upsert_classification(
                    pid, eid, prompt_version=prompt_version,
                    error="article not found in any database",
                )
                errors += 1
                continue

            # The gate prompt is not versioned: an article that passed it
            # before goes straight to extraction (--force asks again).
            gate_passed = None
            if not force and link.get("pass1_relevant") == 1:
                gate_passed = link.get("pass1_confidence") or 0.0

            logger.info("Classifying %s ↔ %s (score=%.2f)", pid, eid[:8], link["relevance_score"])
            result = classifier.classify(
                promise, article,
                body_loader=lambda: _fetch_body(db, fetcher, eid, article),
                gate_passed=gate_passed,
            )

            ps.upsert_classification(
                pid, eid,
                outlet=article["outlet"],
                published_date=article["published"],
                **result,
            )
            if result["error"]:
                errors += 1
            elif result["signal"] == "none":
                irrelevant += 1
            classified += 1

    logger.info(
        "Classified %d links (no evidence=%d, errors=%d)",
        classified, irrelevant, errors,
    )

    best_changes = ps.update_best_articles()
    logger.info(
        "Sticky winners: %d inserted, %d promoted, %d unchanged, %d dropped",
        best_changes["inserted"], best_changes["promoted"],
        best_changes["unchanged"], best_changes["dropped"],
    )

    _maybe_rollup(ps, llm_cfg, skip_rollup)

    return {
        "classified": classified,
        "errors": errors,
        "irrelevant": irrelevant,
        "total_candidates": len(links),
    }


def _format_evidence(counts: Counter) -> str:
    """Render signal counts as ``kept=2, step=1`` for the status log."""
    parts = [f"{v}={n}" for v, n in sorted(counts.items())]
    return "llm-rollup: " + ", ".join(parts) if parts else "llm-rollup"


def _maybe_rollup(
    ps: PromiseStore,
    llm_cfg: Dict[str, Any],
    skip: bool,
    *,
    today: Optional[date] = None,
) -> None:
    """Recompute every promise's status from its evidence.

    The status follows the evidence in both directions, so a promise whose
    evidence turns out to be empty returns to ``made``.  Three kinds of
    promise are left as they are:

    * those with links still waiting to be classified under the current
      prompt, since a verdict on half the evidence would only flicker;
    * those whose status was set by hand (``status_locked``), where a
      disagreement with the evidence is raised as a review flag instead;
    * those in a status only a person assigns.
    """
    rollup_cfg = llm_cfg.get("rollup") or {}
    if skip or not rollup_cfg.get("enabled", True):
        return

    prompt_version = effective_prompt_version(llm_cfg)
    pending = {
        l["promise_id"]
        for l in ps.list_unclassified_links(
            prompt_version, max_attempts=_max_attempts(llm_cfg),
        )
    }
    evidence_by_promise = ps.get_evidence(prompt_version)

    updated = 0
    for promise in ps.list_promises():
        pid = promise["id"]
        if pid in pending:
            continue

        evidence = evidence_by_promise.get(pid, [])
        result = assess(
            evidence,
            deadline=promise.get("deadline"),
            kind=promise_kind(promise),
            today=today,
            min_outlets=int(rollup_cfg.get("min_outlets", 2)),
            grace_days=int(rollup_cfg.get("deadline_grace_days", 30)),
            auto_publish_broken=bool(rollup_cfg.get("auto_publish_broken", False)),
        )
        flags = list(result.flags)
        current = promise["current_status"]
        held = promise.get("status_locked") or current in _MANUAL_ONLY_STATUSES

        if held:
            if result.status != current:
                flags.append(
                    f"{REVIEW_PREFIX} manual status '{current}' differs from "
                    f"evidence-based '{result.status}'"
                )
        elif result.status != current:
            counts = Counter(r["signal"] for r in evidence)
            try:
                ps.update_status(
                    pid, result.status,
                    evidence=_format_evidence(counts),
                    article_ids=[r["article_entry_id"] for r in result.basis],
                    source="rollup",
                )
                updated += 1
            except ValueError as exc:
                logger.warning("Rollup: could not update %s: %s", pid, exc)

        ps.set_review_flags(pid, flags)

    if pending:
        logger.info(
            "Rollup held for %d promises with links awaiting classification",
            len(pending),
        )
    if updated:
        logger.info("Rollup updated %d promise statuses", updated)
