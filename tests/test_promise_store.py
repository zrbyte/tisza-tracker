"""Tests for the LLM-classification additions to PromiseStore.

Covers: schema migration, classification CRUD, the stale-version cache logic
in ``list_unclassified_links``, ``iter_nonirrelevant_classifications``, and
``get_verdict_counts``.
"""

from __future__ import annotations

import sqlite3

import pytest


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_schema_creates_llm_classifications_table(promise_store):
    with sqlite3.connect(promise_store.db_path) as conn:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
    assert "llm_classifications" in tables


def test_schema_verdict_check_constraint(promise_store):
    with pytest.raises(sqlite3.IntegrityError):
        promise_store.upsert_classification(
            "PROM-X", "EID-1",
            verdict="not-a-real-verdict",
            prompt_version="v1",
        )


# ---------------------------------------------------------------------------
# upsert / get classification
# ---------------------------------------------------------------------------


def test_upsert_insert_then_read(promise_store):
    promise_store.upsert_classification(
        "PROM-1", "EID-1",
        verdict="kept", confidence=0.9,
        evidence_quote="quote", reasoning="reason",
        model="m", prompt_version="v1",
        pass1_relevant=True, pass1_confidence=0.8,
    )
    row = promise_store.get_classification("PROM-1", "EID-1")
    assert row is not None
    assert row["verdict"] == "kept"
    assert row["confidence"] == 0.9
    assert row["evidence_quote"] == "quote"
    assert row["pass1_relevant"] == 1  # stored as integer 0/1


def test_upsert_updates_existing(promise_store):
    promise_store.upsert_classification(
        "P", "E", verdict="in_progress", confidence=0.5, prompt_version="v1",
    )
    promise_store.upsert_classification(
        "P", "E", verdict="kept", confidence=0.8, prompt_version="v1",
    )
    row = promise_store.get_classification("P", "E")
    assert row["verdict"] == "kept"
    assert row["confidence"] == 0.8


def test_get_classification_missing_returns_none(promise_store):
    assert promise_store.get_classification("NOPE", "NOPE") is None


def test_upsert_stores_error_without_verdict(promise_store):
    """An LLM failure records an error row with verdict=NULL."""
    promise_store.upsert_classification(
        "P", "E", error="pass1: timeout", prompt_version="v1",
    )
    row = promise_store.get_classification("P", "E")
    assert row["verdict"] is None
    assert row["error"] == "pass1: timeout"


# ---------------------------------------------------------------------------
# list_unclassified_links — the audit-fixed SQL
# ---------------------------------------------------------------------------


def test_list_unclassified_returns_links_with_no_classification(promise_store):
    promise_store.link_article("P", "E1", relevance_score=0.5)
    promise_store.link_article("P", "E2", relevance_score=0.7)
    links = promise_store.list_unclassified_links("v1")
    ids = {l["article_entry_id"] for l in links}
    assert ids == {"E1", "E2"}


def test_list_unclassified_excludes_current_version(promise_store):
    promise_store.link_article("P", "E1", relevance_score=0.5)
    promise_store.upsert_classification(
        "P", "E1", verdict="irrelevant", prompt_version="v1",
    )
    assert promise_store.list_unclassified_links("v1") == []


def test_list_unclassified_includes_stale_version(promise_store):
    promise_store.link_article("P", "E1", relevance_score=0.5)
    promise_store.upsert_classification(
        "P", "E1", verdict="irrelevant", prompt_version="v0",
    )
    links = promise_store.list_unclassified_links("v1")
    assert len(links) == 1
    assert links[0]["article_entry_id"] == "E1"


def test_list_unclassified_force_mode_includes_all(promise_store):
    """The force-mode sentinel version should re-surface every link."""
    promise_store.link_article("P", "E1", relevance_score=0.5)
    promise_store.upsert_classification(
        "P", "E1", verdict="irrelevant", prompt_version="v1",
    )
    links = promise_store.list_unclassified_links("__force__")
    assert len(links) == 1


def test_list_unclassified_null_prompt_version_is_included(promise_store):
    """Rows with NULL prompt_version must not be treated as current."""
    promise_store.link_article("P", "E1", relevance_score=0.5)
    promise_store.upsert_classification(
        "P", "E1", verdict=None, prompt_version=None,
    )
    links = promise_store.list_unclassified_links("v1")
    assert len(links) == 1


def test_list_unclassified_max_per_promise_caps(promise_store):
    for i in range(5):
        promise_store.link_article("P", f"E{i}", relevance_score=0.5 - i * 0.01)
    links = promise_store.list_unclassified_links("v1", max_per_promise=3)
    assert len(links) == 3


def test_list_unclassified_ordered_by_score_desc(promise_store):
    promise_store.link_article("P", "LOW", relevance_score=0.1)
    promise_store.link_article("P", "HIGH", relevance_score=0.9)
    promise_store.link_article("P", "MID", relevance_score=0.5)
    links = promise_store.list_unclassified_links("v1")
    order = [l["article_entry_id"] for l in links]
    assert order == ["HIGH", "MID", "LOW"]


def test_list_unclassified_max_per_promise_applies_per_promise(promise_store):
    for pid in ("P1", "P2"):
        for i in range(4):
            promise_store.link_article(pid, f"{pid}-E{i}", relevance_score=0.5 - i * 0.1)
    links = promise_store.list_unclassified_links("v1", max_per_promise=2)
    assert len(links) == 4  # 2 per promise × 2 promises


# ---------------------------------------------------------------------------
# iter_nonirrelevant_classifications + get_verdict_counts
# ---------------------------------------------------------------------------


def test_iter_nonirrelevant_groups_by_promise(promise_store):
    promise_store.upsert_classification("P1", "E1", verdict="kept", confidence=0.9, prompt_version="v1")
    promise_store.upsert_classification("P1", "E2", verdict="in_progress", confidence=0.5, prompt_version="v1")
    promise_store.upsert_classification("P2", "E3", verdict="broken", confidence=0.8, prompt_version="v1")

    groups = promise_store.iter_nonirrelevant_classifications()
    by_pid = {pid: rows for pid, rows in groups}

    assert set(by_pid.keys()) == {"P1", "P2"}
    assert len(by_pid["P1"]) == 2
    assert len(by_pid["P2"]) == 1


def test_iter_nonirrelevant_excludes_irrelevant_and_nulls(promise_store):
    promise_store.upsert_classification("P1", "E1", verdict="irrelevant", confidence=0.9, prompt_version="v1")
    promise_store.upsert_classification("P1", "E2", verdict=None, error="err", prompt_version="v1")
    promise_store.upsert_classification("P1", "E3", verdict="kept", confidence=0.9, prompt_version="v1")

    groups = dict(promise_store.iter_nonirrelevant_classifications())
    assert list(groups.keys()) == ["P1"]
    assert len(groups["P1"]) == 1
    assert groups["P1"][0]["verdict"] == "kept"


def test_iter_nonirrelevant_empty_when_no_rows(promise_store):
    assert promise_store.iter_nonirrelevant_classifications() == []


def test_get_verdict_counts(promise_store):
    promise_store.upsert_classification("P", "E1", verdict="kept", prompt_version="v1")
    promise_store.upsert_classification("P", "E2", verdict="kept", prompt_version="v1")
    promise_store.upsert_classification("P", "E3", verdict="broken", prompt_version="v1")
    promise_store.upsert_classification("P", "E4", verdict="irrelevant", prompt_version="v1")

    counts = promise_store.get_verdict_counts("P")
    assert counts == {"kept": 2, "broken": 1, "irrelevant": 1}


def test_get_verdict_counts_excludes_null_verdict(promise_store):
    promise_store.upsert_classification("P", "E1", verdict=None, error="fail", prompt_version="v1")
    assert promise_store.get_verdict_counts("P") == {}
