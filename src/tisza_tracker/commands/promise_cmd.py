"""Promise management CLI commands."""

from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Optional

from ..core.config import ConfigManager
from ..core.database import DatabaseManager
from ..core.promise_store import PromiseStore
from ..processors.evidence_ledger import REVIEW_PREFIX, promise_kind
from ..processors.llm_classifier import effective_prompt_version

logger = logging.getLogger(__name__)

# Evidence a reviewer has to read to settle a review flag.
_DECISIVE_SIGNALS = ("kept", "partial", "reversal", "delay")


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
        locked = " (locked)" if p.get("status_locked") else ""
        print(f"  {status_icon} {p['id']}: {p['text'][:80]}{deadline}")
        print(f"      Category: {p['category']} | Status: {p['current_status']}{locked}")


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
    print(f"  Kind: {promise_kind(p)}")
    locked = " (locked: set manually, rollup will not change it)" if p.get("status_locked") else ""
    print(f"  Status: {p['current_status']}{locked}")
    for flag in store.review_flags(p):
        print(f"  Flag: {flag}")
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
            if h.get("article_ids"):
                print(f"      Articles: {h['article_ids']}")

    if links:
        print(f"\n  Linked articles ({len(links)}):")
        for l in links:
            print(f"    [{l['link_type']}] {l['article_entry_id'][:12]}... (score: {l['relevance_score']:.2f})")


def sync_promises(config_path: str) -> dict:
    cm, store = _get_store(config_path)
    yaml_dir = cm.get_promise_yaml_dir()
    return store.sync_from_yaml(yaml_dir)


def update_status(config_path: str, promise_id: str, new_status: str,
                  evidence: Optional[str], article_ids: Optional[list[str]],
                  lock: bool = True) -> None:
    _, store = _get_store(config_path)
    store.update_status(promise_id, new_status, evidence=evidence,
                        article_ids=article_ids, source="manual", lock=lock)


def unlock_status(config_path: str, promise_id: str) -> None:
    _, store = _get_store(config_path)
    store.set_status_lock(promise_id, False)


def review(config_path: str, output_json: bool) -> None:
    """List promises the rollup wants a person to look at, with the evidence."""
    cm, store = _get_store(config_path)
    config = cm.load_config()
    prompt_version = effective_prompt_version(config.get("llm_classification") or {})
    evidence = store.get_evidence(prompt_version)
    db = DatabaseManager(config)

    items = []
    for p in store.list_promises():
        flags = [f for f in store.review_flags(p) if f.startswith(REVIEW_PREFIX)]
        if not flags:
            continue
        rows = []
        for e in evidence.get(p["id"], []):
            text_row = db.get_article_text(e["article_entry_id"]) or {}
            rows.append({**e, "url": text_row.get("url"), "title": text_row.get("title")})
        items.append({
            "id": p["id"], "text": p["text"], "status": p["current_status"],
            "locked": bool(p.get("status_locked")), "kind": promise_kind(p),
            "deadline": p.get("deadline"), "flags": flags, "evidence": rows,
        })
    db.close_all_connections()

    if output_json:
        print(json.dumps(items, indent=2, default=str, ensure_ascii=False))
        return
    if not items:
        print("Nothing to review.")
        return

    for item in items:
        deadline = f", deadline {item['deadline']}" if item["deadline"] else ""
        print(f"\n  {item['id']}: {item['text']}")
        print(f"    Status: {item['status']} ({item['kind']}{deadline})")
        for flag in item["flags"]:
            print(f"    {flag}")
        # Steps and announcements do not decide a review; count them only.
        decisive = [e for e in item["evidence"] if e["signal"] in _DECISIVE_SIGNALS]
        for e in decisive:
            print(f"      [{e['signal']}] {e['published'] or '?'} {e['outlet'] or '?'}: "
                  f"{e['title'] or e['article_entry_id'][:12]}")
            if e.get("reasoning"):
                print(f"          {e['reasoning']}")
            if e.get("url"):
                print(f"          {e['url']}")
        others = Counter(
            e["signal"] for e in item["evidence"] if e["signal"] not in _DECISIVE_SIGNALS
        )
        if others:
            print("      also on record: "
                  + ", ".join(f"{n} {signal}" for signal, n in sorted(others.items())))
    print(f"\n  {len(items)} promise(s) to review (--json lists all evidence). Confirm with: "
          "tt promise status ID STATUS --evidence '...'")


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
