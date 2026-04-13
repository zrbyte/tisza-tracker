"""Promise management CLI commands."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from ..core.config import ConfigManager
from ..core.promise_store import PromiseStore

logger = logging.getLogger(__name__)


def _get_store(config_path: str) -> tuple[ConfigManager, PromiseStore]:
    cm = ConfigManager(config_path)
    config = cm.load_config()
    return cm, PromiseStore(config)


def list_promises(config_path: str, category: Optional[str], status: Optional[str],
                  output_json: bool) -> None:
    _, store = _get_store(config_path)
    promises = store.list_promises(category=category, status=status)

    if output_json:
        print(json.dumps(promises, indent=2, default=str))
        return

    if not promises:
        print("No promises found.")
        return

    for p in promises:
        status_icon = {
            "made": "[ ]", "in_progress": "[~]", "kept": "[+]",
            "broken": "[X]", "partially_kept": "[/]",
            "abandoned": "[-]", "modified": "[*]",
        }.get(p["current_status"], "[?]")
        deadline = f" (deadline: {p['deadline']})" if p.get("deadline") else ""
        print(f"  {status_icon} {p['id']}: {p['text'][:80]}{deadline}")
        print(f"      Category: {p['category']} | Status: {p['current_status']}")


def show_promise(config_path: str, promise_id: str, output_json: bool) -> None:
    _, store = _get_store(config_path)
    p = store.get_promise(promise_id)
    if not p:
        raise ValueError(f"Promise '{promise_id}' not found")

    history = store.get_status_history(promise_id)
    links = store.get_linked_articles(promise_id)

    if output_json:
        print(json.dumps({"promise": p, "history": history, "linked_articles": links},
                         indent=2, default=str))
        return

    print(f"\n  {p['id']}: {p['text']}")
    if p.get("text_en"):
        print(f"  EN: {p['text_en']}")
    print(f"  Category: {p['category']}")
    print(f"  Status: {p['current_status']}")
    if p.get("source"):
        print(f"  Source: {p['source']}")
    if p.get("deadline"):
        print(f"  Deadline: {p['deadline']}")
    if p.get("date_made"):
        print(f"  Date made: {p['date_made']}")
    if p.get("keywords"):
        print(f"  Keywords: {p['keywords']}")

    if history:
        print(f"\n  Status history ({len(history)} changes):")
        for h in history:
            print(f"    {h['changed_at']}: {h['old_status']} -> {h['new_status']}")
            if h.get("evidence"):
                print(f"      Evidence: {h['evidence']}")

    if links:
        print(f"\n  Linked articles ({len(links)}):")
        for l in links:
            print(f"    [{l['link_type']}] {l['article_entry_id'][:12]}... (score: {l['relevance_score']:.2f})")


def sync_promises(config_path: str) -> dict:
    cm, store = _get_store(config_path)
    yaml_dir = cm.get_promise_yaml_dir()
    return store.sync_from_yaml(yaml_dir)


def update_status(config_path: str, promise_id: str, new_status: str,
                  evidence: Optional[str], article_ids: Optional[list[str]]) -> None:
    _, store = _get_store(config_path)
    store.update_status(promise_id, new_status, evidence=evidence, article_ids=article_ids)


def link_article(config_path: str, promise_id: str, entry_id: str,
                 score: float) -> None:
    _, store = _get_store(config_path)
    store.link_article(promise_id, entry_id, relevance_score=score, link_type="manual")


def stats(config_path: str, output_json: bool) -> None:
    _, store = _get_store(config_path)
    s = store.get_stats()

    if output_json:
        print(json.dumps(s, indent=2, default=str))
        return

    print(f"\n  Total promises: {s['total_promises']}")
    if s["by_status"]:
        print("  By status:")
        for st, cnt in sorted(s["by_status"].items()):
            print(f"    {st}: {cnt}")
    if s["by_category"]:
        print("  By category:")
        for cat, cnt in sorted(s["by_category"].items()):
            print(f"    {cat}: {cnt}")
    print(f"  Total article links: {s['total_article_links']}")
