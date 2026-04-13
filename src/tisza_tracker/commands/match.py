"""Match command: link filtered articles to promises by semantic similarity."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from ..core.config import ConfigManager
from ..core.database import DatabaseManager
from ..core.promise_store import PromiseStore
from ..core.command_utils import resolve_topics
from ..processors.promise_matcher import PromiseMatcher

logger = logging.getLogger(__name__)


# Map topic names to promise categories.
# By default, the topic name IS the category. Override here for non-obvious mappings.
_TOPIC_CATEGORY_MAP: Dict[str, str] = {
    "altalanos": "altalanos",
}


def run(
    config_path: str,
    topic: Optional[str] = None,
    threshold: float = 0.3,
    output_json: bool = False,
) -> Optional[Dict[str, Any]]:
    """Run promise-article matching for one or all topics."""
    cm = ConfigManager(config_path)
    config = cm.load_config()
    db = DatabaseManager(config)
    ps = PromiseStore(config)

    # Sync promises from YAML first
    yaml_dir = cm.get_promise_yaml_dir()
    ps.sync_from_yaml(yaml_dir)

    topics_to_process = resolve_topics(cm, topic)
    if not topics_to_process:
        logger.warning("No topics to process")
        return None

    # Determine model from first topic config (all topics use the same model)
    first_topic_cfg = cm.load_topic_config(topics_to_process[0])
    ranking_cfg = first_topic_cfg.get("ranking", {}) or {}
    model_name = ranking_cfg.get("model", "paraphrase-multilingual-MiniLM-L12-v2")

    matcher = PromiseMatcher(db, ps, model_name=model_name)

    results = {}
    for topic_name in topics_to_process:
        # Map topic to promise category
        category = _TOPIC_CATEGORY_MAP.get(topic_name, topic_name)

        # Check topic-level matching config
        topic_cfg = cm.load_topic_config(topic_name)
        match_cfg = topic_cfg.get("promise_matching", {}) or {}
        if match_cfg.get("enabled") is False:
            logger.info("Promise matching disabled for topic '%s'", topic_name)
            continue

        topic_threshold = match_cfg.get("min_relevance", threshold)
        max_links = match_cfg.get("max_links_per_promise", 50)

        result = matcher.match_topic(
            topic_name, category,
            threshold=topic_threshold,
            max_links=max_links,
        )
        results[topic_name] = result
        logger.info(
            "Topic '%s': matched %d articles to promises",
            topic_name, result["matched"],
        )

    return results if output_json else None
