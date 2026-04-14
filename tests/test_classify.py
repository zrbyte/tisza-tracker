"""Tests for the classify command's rollup logic and formatting helpers."""

from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from tisza_tracker.commands.classify import (
    _format_evidence,
    _load_llm_config,
    _resolve_article,
    _rollup_status,
)


DEFAULT_CFG = {
    "broken_min_confidence": 0.7,
    "kept_min_votes": 2,
    "kept_min_confidence": 0.6,
    "in_progress_min_confidence": 0.5,
}


def test_rollup_broken_wins_with_single_confident_vote():
    classifications = [
        {"verdict": "kept", "confidence": 0.9},
        {"verdict": "kept", "confidence": 0.9},
        {"verdict": "broken", "confidence": 0.8},
    ]
    assert _rollup_status(DEFAULT_CFG, classifications) == "broken"


def test_rollup_broken_ignored_below_threshold():
    classifications = [
        {"verdict": "broken", "confidence": 0.5},  # below 0.7
        {"verdict": "kept", "confidence": 0.9},
        {"verdict": "kept", "confidence": 0.9},
    ]
    assert _rollup_status(DEFAULT_CFG, classifications) == "kept"


def test_rollup_kept_needs_quorum():
    classifications = [{"verdict": "kept", "confidence": 0.9}]
    # Single kept vote → not enough, falls to in_progress
    assert _rollup_status(DEFAULT_CFG, classifications) == "in_progress"


def test_rollup_kept_meets_quorum():
    classifications = [
        {"verdict": "kept", "confidence": 0.7},
        {"verdict": "kept", "confidence": 0.8},
    ]
    assert _rollup_status(DEFAULT_CFG, classifications) == "kept"


def test_rollup_kept_quorum_counts_only_confident():
    classifications = [
        {"verdict": "kept", "confidence": 0.9},
        {"verdict": "kept", "confidence": 0.3},  # below kept_min_confidence
    ]
    # Only one confident kept → in_progress (via kept fallback branch)
    assert _rollup_status(DEFAULT_CFG, classifications) == "in_progress"


def test_rollup_in_progress_from_single_vote():
    classifications = [{"verdict": "in_progress", "confidence": 0.6}]
    assert _rollup_status(DEFAULT_CFG, classifications) == "in_progress"


def test_rollup_low_confidence_returns_none():
    classifications = [
        {"verdict": "kept", "confidence": 0.1},
        {"verdict": "in_progress", "confidence": 0.1},
    ]
    assert _rollup_status(DEFAULT_CFG, classifications) is None


def test_rollup_ignores_unknown_verdicts():
    """Strings outside kept/broken/in_progress should not count toward any bucket."""
    classifications = [
        {"verdict": "irrelevant", "confidence": 0.99},
        {"verdict": "bogus", "confidence": 0.99},
    ]
    assert _rollup_status(DEFAULT_CFG, classifications) is None


def test_rollup_handles_missing_confidence():
    classifications = [{"verdict": "in_progress", "confidence": None}]
    assert _rollup_status(DEFAULT_CFG, classifications) is None


def test_rollup_empty_input_returns_none():
    assert _rollup_status(DEFAULT_CFG, []) is None


# ---------------------------------------------------------------------------
# _format_evidence
# ---------------------------------------------------------------------------


def test_format_evidence_single_verdict():
    assert _format_evidence(Counter({"kept": 2})) == "llm-rollup: kept=2"


def test_format_evidence_sorted_keys():
    """Output ordering must be deterministic for stable commit diffs."""
    out = _format_evidence(Counter({"kept": 2, "broken": 1, "in_progress": 3}))
    assert out == "llm-rollup: broken=1, in_progress=3, kept=2"


def test_format_evidence_empty_counter():
    assert _format_evidence(Counter()) == "llm-rollup"


# ---------------------------------------------------------------------------
# End-to-end rollup via the public helper (exercises the whole path)
# ---------------------------------------------------------------------------


def test_rollup_full_pipeline(promise_store):
    """Seed classifications, run _maybe_rollup, verify status flips."""
    from tisza_tracker.commands.classify import _maybe_rollup

    promise_store.add_promise("P-KEPT", "kept promise", "gazdasag")
    promise_store.add_promise("P-BROKEN", "broken promise", "gazdasag")
    promise_store.add_promise("P-NO-CHANGE", "unclassified", "gazdasag")

    # P-KEPT: two confident kept votes → should become 'kept'
    promise_store.upsert_classification("P-KEPT", "E1", verdict="kept", confidence=0.9, prompt_version="v1")
    promise_store.upsert_classification("P-KEPT", "E2", verdict="kept", confidence=0.7, prompt_version="v1")

    # P-BROKEN: one confident broken vote → should become 'broken'
    promise_store.upsert_classification("P-BROKEN", "E3", verdict="broken", confidence=0.9, prompt_version="v1")

    # P-NO-CHANGE: irrelevant only → status unchanged
    promise_store.upsert_classification("P-NO-CHANGE", "E4", verdict="irrelevant", confidence=0.9, prompt_version="v1")

    llm_cfg = {"rollup": {"enabled": True, **DEFAULT_CFG}}
    _maybe_rollup(promise_store, llm_cfg, skip=False)

    assert promise_store.get_promise("P-KEPT")["current_status"] == "kept"
    assert promise_store.get_promise("P-BROKEN")["current_status"] == "broken"
    assert promise_store.get_promise("P-NO-CHANGE")["current_status"] == "made"


def test_rollup_skip_flag_bypasses(promise_store):
    from tisza_tracker.commands.classify import _maybe_rollup

    promise_store.add_promise("P", "t", "gazdasag")
    promise_store.upsert_classification("P", "E1", verdict="broken", confidence=0.9, prompt_version="v1")
    promise_store.upsert_classification("P", "E2", verdict="broken", confidence=0.9, prompt_version="v1")

    llm_cfg = {"rollup": {"enabled": True, **DEFAULT_CFG}}
    _maybe_rollup(promise_store, llm_cfg, skip=True)
    assert promise_store.get_promise("P")["current_status"] == "made"


def test_rollup_disabled_in_config_bypasses(promise_store):
    from tisza_tracker.commands.classify import _maybe_rollup

    promise_store.add_promise("P", "t", "gazdasag")
    promise_store.upsert_classification("P", "E", verdict="broken", confidence=0.9, prompt_version="v1")

    _maybe_rollup(promise_store, {"rollup": {"enabled": False}}, skip=False)
    assert promise_store.get_promise("P")["current_status"] == "made"


def test_rollup_records_history_with_formatted_evidence(promise_store):
    """The evidence written to promise_status_history should use the pretty format."""
    from tisza_tracker.commands.classify import _maybe_rollup

    promise_store.add_promise("P", "t", "gazdasag")
    promise_store.upsert_classification("P", "E1", verdict="broken", confidence=0.9, prompt_version="v1")

    llm_cfg = {"rollup": {"enabled": True, **DEFAULT_CFG}}
    _maybe_rollup(promise_store, llm_cfg, skip=False)

    history = promise_store.get_status_history("P")
    # Exactly one flip recorded
    assert len(history) == 1
    assert history[0]["evidence"] == "llm-rollup: broken=1"


# ---------------------------------------------------------------------------
# _load_llm_config
# ---------------------------------------------------------------------------


def test_load_llm_config_missing_block_defaults_to_disabled():
    assert _load_llm_config({})["enabled"] is False


def test_load_llm_config_preserves_existing_values():
    cfg = _load_llm_config({"llm_classification": {"enabled": True, "model": "foo"}})
    assert cfg["enabled"] is True
    assert cfg["model"] == "foo"


def test_load_llm_config_handles_null_block():
    """A user can write ``llm_classification:`` with no value, giving None."""
    assert _load_llm_config({"llm_classification": None})["enabled"] is False


# ---------------------------------------------------------------------------
# _resolve_article — three-DB fallback cascade
# ---------------------------------------------------------------------------


class _FakeDB:
    """Minimal stand-in for DatabaseManager exposing the methods used by
    ``_resolve_article``: ``get_article_text`` + ``get_connection``."""

    def __init__(self, article_text=None, current_rows=None, history_rows=None):
        self._article_text = article_text or {}
        self._current = current_rows or {}
        self._history = history_rows or {}
        self.queries = []

    def get_article_text(self, entry_id):
        self.queries.append(("article_text", entry_id))
        return self._article_text.get(entry_id)

    def get_connection(self, db_key, row_factory=True):
        self.queries.append((db_key, None))
        source = self._current if db_key == "current" else self._history

        class _Cursor:
            def execute(self_inner, sql, params):
                entry_id = params[0]
                row = source.get(entry_id)
                self_inner._row = row
                return self_inner

            def fetchone(self_inner):
                return self_inner._row

        class _Conn:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *args):
                return False

            def execute(self_inner, sql, params):
                return _Cursor().execute(sql, params)

        return _Conn()


def test_resolve_article_prefers_article_text_db():
    db = _FakeDB(article_text={
        "E1": {"title": "AT title", "summary": "AT summary", "full_text": "AT body"},
    })
    title, summary, full_text = _resolve_article(db, "E1")
    assert title == "AT title"
    assert summary == "AT summary"
    assert full_text == "AT body"


def test_resolve_article_falls_back_to_papers():
    db = _FakeDB(current_rows={
        "E1": {"title": "From papers", "summary": "p summary"},
    })
    title, summary, full_text = _resolve_article(db, "E1")
    assert title == "From papers"
    assert summary == "p summary"
    assert full_text is None


def test_resolve_article_falls_back_to_history():
    db = _FakeDB(history_rows={
        "E1": {"title": "From history", "summary": "h summary"},
    })
    title, summary, full_text = _resolve_article(db, "E1")
    assert title == "From history"
    assert summary == "h summary"
    assert full_text is None


def test_resolve_article_returns_none_when_nowhere_found():
    assert _resolve_article(_FakeDB(), "NOPE") is None


def test_resolve_article_skips_empty_article_text_row():
    """A row with only NULL/empty fields shouldn't short-circuit the cascade."""
    db = _FakeDB(
        article_text={"E1": {"title": None, "summary": None, "full_text": None}},
        current_rows={"E1": {"title": "real title", "summary": "s"}},
    )
    title, summary, full_text = _resolve_article(db, "E1")
    assert title == "real title"
    assert full_text is None


def test_resolve_article_handles_article_text_with_only_title():
    """A paywalled/failed fetch may have title but no body; that still wins."""
    db = _FakeDB(article_text={
        "E1": {"title": "just the headline", "summary": None, "full_text": None},
    })
    title, summary, full_text = _resolve_article(db, "E1")
    assert title == "just the headline"
    assert summary == ""
    assert full_text is None
