"""Promise-article matching processor.

After filter and rank, scores all filtered articles against promises in the
matching category. Uses each promise's ranking_query as the semantic query
and links articles above a relevance threshold to the promise.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..core.database import DatabaseManager
from ..core.promise_store import PromiseStore
from .st_ranker import STRanker

logger = logging.getLogger(__name__)


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

        # Build entry text batch once
        batch = [
            (e["id"], e["topic"], f"{e.get('title', '')} {e.get('summary', '')}")
            for e in entries
        ]

        total_links = 0
        for promise in promises:
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
                    "Promise %s: linked %d articles (threshold=%.2f)",
                    promise["id"], linked, threshold,
                )
            total_links += linked

        return {
            "topic": topic_name,
            "category": category,
            "matched": total_links,
            "promises_checked": len(promises),
        }
