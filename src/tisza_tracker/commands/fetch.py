"""
Fetch command: store article text in ``article_text.db``.

For **all** ranked entries the RSS title + summary are saved (no HTTP
requests — this is just copying metadata already in papers.db).

For entries whose ``rank_score`` meets the configured fetch threshold
the full article body is additionally downloaded via trafilatura.

Entries that already have a row in article_text.db are skipped
(idempotent).  Pass ``--force`` to re-fetch them.
"""

from __future__ import annotations

import logging
from typing import Optional, Dict, Any

from ..core.config import ConfigManager
from ..core.database import DatabaseManager
from ..core.command_utils import resolve_topics
from ..processors.article_fetcher import ArticleFetcher

logger = logging.getLogger(__name__)


def run(
    config_path: str,
    topic: Optional[str] = None,
    *,
    threshold: Optional[float] = None,
    force: bool = False,
    output_json: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Store article text for ranked entries in article_text.db.

    All ranked entries get their RSS title + summary saved.  Entries
    above *threshold* also get their full body text fetched.

    Args:
        config_path: Path to main config
        topic: Optional topic name; if None, process all topics
        threshold: Minimum rank_score for full-text fetch (overrides config)
        force: Re-fetch entries that already have text
        output_json: When True, suppress log noise and return a result dict.

    Returns:
        Result dict when *output_json* is True, otherwise None.
    """
    if output_json:
        logging.getLogger("tisza_tracker").setLevel(logging.WARNING)
    logger.info("Starting fetch command")

    cfg_mgr = ConfigManager(config_path)
    if not cfg_mgr.validate_config():
        raise ValueError("Configuration validation failed")

    config = cfg_mgr.load_config()
    db = DatabaseManager(config)

    defaults = config.get("defaults") or {}
    fetch_threshold = threshold if threshold is not None else float(defaults.get("fetch_threshold", 0.40))

    topics = resolve_topics(cfg_mgr, topic)
    topic_results: Dict[str, Dict[str, int]] = {}

    with ArticleFetcher() as fetcher:
        for topic_name in topics:
            stored = 0
            fetched = 0
            skipped = 0
            failed = 0

            entries = db.get_current_entries(topic=topic_name, status="ranked")
            if not entries:
                logger.info("No ranked entries for topic '%s'", topic_name)
                topic_results[topic_name] = {
                    "stored": 0, "fetched": 0, "skipped": 0, "failed": 0,
                }
                continue

            for entry in entries:
                entry_id = entry["id"]
                url = entry.get("link", "")
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                score = entry.get("rank_score") or 0

                if not force and db.has_article_text(entry_id):
                    skipped += 1
                    continue

                above_threshold = score >= fetch_threshold and url

                if above_threshold:
                    text, status = fetcher.fetch_text(url)
                    db.save_article_text(
                        entry_id, url or "", text,
                        fetch_status=status, title=title, summary=summary,
                    )
                    if status == "ok":
                        fetched += 1
                        logger.debug("Fetched %s (%d chars)", entry_id[:8], len(text or ""))
                    else:
                        failed += 1
                        logger.warning("Entry %s fetch '%s': %s", entry_id[:8], status, url)
                else:
                    # Below threshold — save RSS metadata only (no HTTP request)
                    db.save_article_text(
                        entry_id, url or "", None,
                        fetch_status="ok", title=title, summary=summary,
                    )

                stored += 1

            logger.info(
                "Topic '%s': stored=%d (fetched=%d, summary-only=%d), skipped=%d, failed=%d",
                topic_name, stored, fetched, stored - fetched - failed, skipped, failed,
            )
            topic_results[topic_name] = {
                "stored": stored,
                "fetched": fetched,
                "skipped": skipped,
                "failed": failed,
            }

    db.close_all_connections()
    logger.info("Fetch command completed")

    if output_json:
        return {
            "command": "fetch",
            "threshold": fetch_threshold,
            "topics": topic_results,
            "total_stored": sum(t["stored"] for t in topic_results.values()),
            "total_fetched": sum(t["fetched"] for t in topic_results.values()),
            "total_failed": sum(t["failed"] for t in topic_results.values()),
        }
    return None
