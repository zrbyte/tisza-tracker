"""Promise-article matching processor.

After filter and rank, scores all filtered articles against promises in the
matching category.  For each promise:

1. **Pre-filter** — if the promise has a ``filter_pattern``, only articles
   whose *title + summary* match the regex proceed to semantic scoring.
   This keeps the expensive embedding step focused.
2. **Semantic score** — the promise's ``ranking_query`` (or its ``text``
   as fallback) is compared against each candidate's *title + summary*
   via Sentence-Transformers cosine similarity.
3. **Link** — articles above the relevance threshold are linked to the
   promise in the ``promise_article_links`` table.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from ..core.database import DatabaseManager
from ..core.promise_store import PromiseStore
from .st_ranker import STRanker

logger = logging.getLogger(__name__)


def _entry_text(entry: Dict[str, Any]) -> str:
    """Combine title and summary for matching."""
    title = (entry.get("title") or "").strip()
    summary = (entry.get("summary") or "").strip()
    return f"{title} {summary}".strip()


class PromiseMatcher:
    """Scores articles against promises and creates links."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        promise_store: PromiseStore,
        model_name: str = "paraphrase-multilingual-MiniLM-L12-v2",
    ) -> None:
        self.db = db_manager
        self.promises = promise_store
        self.ranker = STRanker(model_name=model_name)

    def match_topic(
        self,
        topic_name: str,
        category: str,
        threshold: float = 0.3,
        max_links: int = 50,
    ) -> Dict[str, Any]:
        """Score articles for a topic against all promises in the category.

        Returns summary of matches made.
        """
        promises = self.promises.list_promises(category=category)
        if not promises:
            logger.info("No promises for category '%s'", category)
            return {"topic": topic_name, "category": category, "matched": 0, "promises_checked": 0}

        entries = self.db.get_current_entries(topic=topic_name)
        if not entries:
            logger.info("No entries for topic '%s'", topic_name)
            return {"topic": topic_name, "category": category, "matched": 0, "promises_checked": len(promises)}

        if not self.ranker.available():
            logger.warning("Ranker not available; skipping promise matching for '%s'", topic_name)
            return {"topic": topic_name, "category": category, "matched": 0, "promises_checked": len(promises)}

        total_links = 0
        for promise in promises:
            # Pre-filter by regex if the promise defines one
            candidates = self._prefilter(entries, promise.get("filter_pattern"))

            if not candidates:
                logger.debug(
                    "Promise %s: no candidates after pre-filter (%d entries checked)",
                    promise["id"], len(entries),
                )
                continue

            # Build batch for semantic scoring — title + summary
            batch = [
                (e["id"], e["topic"], _entry_text(e))
                for e in candidates
            ]

            query = promise.get("ranking_query") or promise["text"]
            scores = self.ranker.score_entries(query, batch)

            linked = 0
            for entry_id, _, score in scores:
                if float(score) >= threshold and linked < max_links:
                    self.promises.link_article(
                        promise["id"], entry_id,
                        relevance_score=float(score), link_type="auto",
                    )
                    linked += 1

            if linked > 0:
                logger.info(
                    "Promise %s: linked %d articles (of %d candidates, threshold=%.2f)",
                    promise["id"], linked, len(candidates), threshold,
                )
            total_links += linked

        return {
            "topic": topic_name,
            "category": category,
            "matched": total_links,
            "promises_checked": len(promises),
        }

    @staticmethod
    def _prefilter(
        entries: List[Dict[str, Any]],
        pattern: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Return entries whose title+summary match *pattern*.

        If *pattern* is None or empty, all entries pass through.
        """
        if not pattern:
            return entries

        try:
            rx = re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            logger.warning("Invalid filter_pattern '%s': %s — skipping pre-filter", pattern, exc)
            return entries

        return [e for e in entries if rx.search(_entry_text(e))]
