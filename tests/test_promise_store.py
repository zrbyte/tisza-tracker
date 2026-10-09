"""Tests for the LLM-classification side of PromiseStore.

Covers: schema migration, classification CRUD, the cache and retry logic in
``list_unclassified_links``, ``get_evidence``, the sticky best article, and
manual status locks.
"""

from __future__ import annotations

import sqlite3

import pytest

from tisza_tracker.core.promise_store import PromiseStore


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


_LEGACY_SCHEMA = """
CREATE TABLE promises (
    id TEXT PRIMARY KEY, text TEXT NOT NULL, text_en TEXT, source TEXT,
    source_url TEXT, date_made TEXT, category TEXT NOT NULL, subcategory TEXT,
    deadline TEXT, keywords TEXT, ranking_query TEXT, filter_pattern TEXT,
    current_status TEXT DEFAULT 'made', status_updated TEXT, notes TEXT,
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE promise_status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT, promise_id TEXT NOT NULL,
    old_status TEXT, new_status TEXT NOT NULL,
    changed_at TEXT DEFAULT (datetime('now')), evidence TEXT, article_ids TEXT
);
CREATE TABLE promise_article_links (
    promise_id TEXT NOT NULL, article_entry_id TEXT NOT NULL, relevance_score REAL,
    linked_at TEXT DEFAULT (datetime('now')), link_type TEXT DEFAULT 'auto',
    PRIMARY KEY (promise_id, article_entry_id)
);
CREATE TABLE llm_classifications (
    promise_id TEXT NOT NULL, article_entry_id TEXT NOT NULL,
    verdict TEXT CHECK(verdict IN ('kept','in_progress','broken','irrelevant')),
    confidence REAL, evidence_quote TEXT, reasoning TEXT, model TEXT,
    prompt_version TEXT, pass1_relevant INTEGER, pass1_confidence REAL, error TEXT,
    classified_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (promise_id, article_entry_id)
);
"""


@pytest.fixture
def legacy_store(tmp_data_dir) -> PromiseStore:
    """A promises.db written by the release before signals existed."""
    conn = sqlite3.connect(tmp_data_dir / "promises.db")
    conn.executescript(_LEGACY_SCHEMA)
    conn.execute(
        "INSERT INTO promises (id, text, category, current_status) "
        "VALUES ('P', 'promise', 'gazdasag', 'broken')"
    )
    rows = [
        ("P", "GATED", "irrelevant", 0.7, "v1", 0),
        ("P", "BROKEN", "broken", 0.8, "v1", 1),
        ("P", "KEPT", "kept", 0.9, "v1", 1),
    ]
    for pid, eid, verdict, conf, version, relevant in rows:
        conn.execute(
            "INSERT INTO promise_article_links (promise_id, article_entry_id, relevance_score) "
            "VALUES (?, ?, 0.5)", (pid, eid),
        )
        conn.execute(
            "INSERT INTO llm_classifications (promise_id, article_entry_id, verdict, "
            "confidence, prompt_version, pass1_relevant) VALUES (?, ?, ?, ?, ?, ?)",
            (pid, eid, verdict, conf, version, relevant),
        )
    conn.commit()
    conn.close()
    return PromiseStore({"database": {"promises_path": "promises.db"}})


def test_migration_adds_columns_and_keeps_rows(legacy_store):
    promise = legacy_store.get_promise("P")
    assert promise["current_status"] == "broken"
    assert promise["status_locked"] == 0
    assert promise["kind"] is None
    assert promise["review_flags"] is None

    kept = legacy_store.get_classification("P", "KEPT")
    assert kept["verdict"] == "kept"
    assert kept["signal"] is None  # old verdicts are not evidence
    assert kept["attempts"] == 0


def test_migration_marks_gate_rejections_as_no_signal(legacy_store):
    assert legacy_store.get_classification("P", "GATED")["signal"] == "none"


def test_migration_is_idempotent(legacy_store):
    again = PromiseStore({"database": {"promises_path": "promises.db"}})
    assert again.get_classification("P", "KEPT")["verdict"] == "kept"


def test_migrated_verdicts_are_reclassified_but_gate_rejections_are_not(legacy_store):
    """After the upgrade only links that passed the gate need new work, and
    none of the old verdicts counts as evidence in the meantime."""
    pending = {l["article_entry_id"] for l in legacy_store.list_unclassified_links("v1.r2")}
    assert pending == {"BROKEN", "KEPT"}
    assert legacy_store.get_evidence("v1.r2") == {}
    assert legacy_store.get_evidence() == {}


# ---------------------------------------------------------------------------
# upsert / get classification
# ---------------------------------------------------------------------------


def test_upsert_insert_then_read(promise_store):
    promise_store.upsert_classification(
        "PROM-1", "EID-1",
        signal="kept", confidence=0.9,
        evidence_quote="quote", quote_verbatim=True, reasoning="reason",
        actor="current_government", evidence_type="delivered", scope="full",
        event_date="2026-06-09", outlet="Telex", published_date="2026-06-10",
        body_chars=1200, model="m", prompt_version="v1",
        pass1_relevant=True, pass1_confidence=0.8,
    )
    row = promise_store.get_classification("PROM-1", "EID-1")
    assert row is not None
    assert row["signal"] == "kept"
    assert row["verdict"] == "kept"
    assert row["confidence"] == 0.9
    assert row["evidence_quote"] == "quote"
    assert row["quote_verbatim"] == 1
    assert row["actor"] == "current_government"
    assert row["outlet"] == "Telex"
    assert row["published_date"] == "2026-06-10"
    assert row["body_chars"] == 1200
    assert row["pass1_relevant"] == 1  # stored as integer 0/1
    assert row["attempts"] == 1


@pytest.mark.parametrize("signal,verdict", [
    ("kept", "kept"), ("partial", "kept"), ("step", "in_progress"),
    ("intent", "in_progress"), ("delay", "in_progress"),
    ("reversal", "broken"), ("none", "irrelevant"),
])
def test_upsert_derives_coarse_verdict_from_signal(promise_store, signal, verdict):
    promise_store.upsert_classification("P", "E", signal=signal, prompt_version="v1")
    assert promise_store.get_classification("P", "E")["verdict"] == verdict


def test_upsert_updates_existing(promise_store):
    promise_store.upsert_classification(
        "P", "E", signal="step", confidence=0.5, prompt_version="v1",
    )
    promise_store.upsert_classification(
        "P", "E", signal="kept", confidence=0.8, prompt_version="v1",
    )
    row = promise_store.get_classification("P", "E")
    assert row["signal"] == "kept"
    assert row["confidence"] == 0.8


def test_get_classification_missing_returns_none(promise_store):
    assert promise_store.get_classification("NOPE", "NOPE") is None


def test_upsert_stores_error_without_signal(promise_store):
    """An LLM failure records an error row with no signal or verdict."""
    promise_store.upsert_classification(
        "P", "E", error="pass1: timeout", prompt_version="v1",
    )
    row = promise_store.get_classification("P", "E")
    assert row["signal"] is None
    assert row["verdict"] is None
    assert row["error"] == "pass1: timeout"


def test_upsert_counts_attempts_per_prompt_version(promise_store):
    for _ in range(3):
        promise_store.upsert_classification("P", "E", error="boom", prompt_version="v1")
    assert promise_store.get_classification("P", "E")["attempts"] == 3

    promise_store.upsert_classification("P", "E", error="boom", prompt_version="v2")
    assert promise_store.get_classification("P", "E")["attempts"] == 1


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
        "P", "E1", signal="step", pass1_relevant=True, prompt_version="v1",
    )
    assert promise_store.list_unclassified_links("v1") == []


def test_list_unclassified_includes_stale_version(promise_store):
    promise_store.link_article("P", "E1", relevance_score=0.5)
    promise_store.upsert_classification(
        "P", "E1", signal="step", pass1_relevant=True, prompt_version="v0",
    )
    links = promise_store.list_unclassified_links("v1")
    assert len(links) == 1
    assert links[0]["article_entry_id"] == "E1"


def test_list_unclassified_keeps_gate_rejections_across_versions(promise_store):
    """prompt_version covers the extraction pass; an article the relevance
    gate rejected does not need a second look when that prompt changes."""
    promise_store.link_article("P", "E1", relevance_score=0.5)
    promise_store.upsert_classification(
        "P", "E1", signal="none", pass1_relevant=False, prompt_version="v0",
    )
    assert promise_store.list_unclassified_links("v1") == []


def test_list_unclassified_stale_no_signal_from_pass2_is_redone(promise_store):
    """A `none` that pass 2 produced is a judgement of the old prompt."""
    promise_store.link_article("P", "E1", relevance_score=0.5)
    promise_store.upsert_classification(
        "P", "E1", signal="none", pass1_relevant=True, prompt_version="v0",
    )
    assert len(promise_store.list_unclassified_links("v1")) == 1


def test_list_unclassified_force_mode_includes_all(promise_store):
    """Force re-surfaces every link, gate rejections included."""
    promise_store.link_article("P", "E1", relevance_score=0.5)
    promise_store.link_article("P", "E2", relevance_score=0.4)
    promise_store.upsert_classification(
        "P", "E1", signal="none", pass1_relevant=False, prompt_version="v1",
    )
    promise_store.upsert_classification(
        "P", "E2", signal="kept", pass1_relevant=True, prompt_version="v1",
    )
    assert promise_store.list_unclassified_links("v1") == []
    assert len(promise_store.list_unclassified_links("v1", force=True)) == 2


def test_list_unclassified_null_prompt_version_is_included(promise_store):
    """Rows with NULL prompt_version must not be treated as current."""
    promise_store.link_article("P", "E1", relevance_score=0.5)
    promise_store.upsert_classification(
        "P", "E1", verdict=None, prompt_version=None,
    )
    links = promise_store.list_unclassified_links("v1")
    assert len(links) == 1


def test_list_unclassified_retries_failed_rows(promise_store):
    """A failed LLM call must not be cached as if it were a result."""
    promise_store.link_article("P", "E1", relevance_score=0.5)
    promise_store.upsert_classification("P", "E1", error="pass2: timeout", prompt_version="v1")
    assert len(promise_store.list_unclassified_links("v1")) == 1


def test_list_unclassified_gives_up_after_max_attempts(promise_store):
    promise_store.link_article("P", "E1", relevance_score=0.5)
    for _ in range(3):
        promise_store.upsert_classification("P", "E1", error="boom", prompt_version="v1")
    assert promise_store.list_unclassified_links("v1", max_attempts=3) == []
    assert len(promise_store.list_unclassified_links("v1", max_attempts=5)) == 1
    # A new prompt version starts the count again.
    assert len(promise_store.list_unclassified_links("v2", max_attempts=3)) == 1


def test_list_unclassified_retry_success_clears_the_link(promise_store):
    promise_store.link_article("P", "E1", relevance_score=0.5)
    promise_store.upsert_classification("P", "E1", error="boom", prompt_version="v1")
    promise_store.upsert_classification(
        "P", "E1", signal="step", pass1_relevant=True, prompt_version="v1",
    )
    assert promise_store.list_unclassified_links("v1") == []
    assert promise_store.get_classification("P", "E1")["error"] is None


def test_list_unclassified_carries_the_stored_gate_result(promise_store):
    promise_store.link_article("P", "NEW", relevance_score=0.9)
    promise_store.link_article("P", "STALE", relevance_score=0.5)
    promise_store.upsert_classification(
        "P", "STALE", signal="step", pass1_relevant=True, pass1_confidence=0.8,
        prompt_version="v0",
    )
    new, stale = promise_store.list_unclassified_links("v1")
    assert (new["pass1_relevant"], new["pass1_confidence"]) == (None, None)
    assert (stale["pass1_relevant"], stale["pass1_confidence"]) == (1, 0.8)


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
# get_evidence + get_signal_counts
# ---------------------------------------------------------------------------


def test_get_evidence_groups_by_promise(promise_store):
    promise_store.upsert_classification(
        "P1", "E1", signal="kept", confidence=0.9, outlet="Telex",
        published_date="2026-06-10", prompt_version="v1",
    )
    promise_store.upsert_classification("P1", "E2", signal="step", confidence=0.5, prompt_version="v1")
    promise_store.upsert_classification("P2", "E3", signal="reversal", confidence=0.8, prompt_version="v1")

    evidence = promise_store.get_evidence("v1")

    assert set(evidence) == {"P1", "P2"}
    assert len(evidence["P1"]) == 2
    assert len(evidence["P2"]) == 1
    kept = next(r for r in evidence["P1"] if r["signal"] == "kept")
    assert kept["outlet"] == "Telex"
    assert kept["published"] == "2026-06-10"
    assert kept["article_entry_id"] == "E1"


def test_get_evidence_excludes_no_signal_and_errors(promise_store):
    promise_store.upsert_classification("P1", "E1", signal="none", confidence=0.9, prompt_version="v1")
    promise_store.upsert_classification("P1", "E2", error="err", prompt_version="v1")
    promise_store.upsert_classification("P1", "E3", signal="kept", confidence=0.9, prompt_version="v1")

    evidence = promise_store.get_evidence("v1")
    assert list(evidence) == ["P1"]
    assert [r["signal"] for r in evidence["P1"]] == ["kept"]


def test_get_evidence_ignores_other_prompt_versions(promise_store):
    """Verdicts of a superseded prompt must not reach the rollup."""
    promise_store.upsert_classification("P", "OLD", signal="reversal", prompt_version="v0")
    promise_store.upsert_classification("P", "NEW", signal="step", prompt_version="v1")

    assert [r["article_entry_id"] for r in promise_store.get_evidence("v1")["P"]] == ["NEW"]
    assert len(promise_store.get_evidence()["P"]) == 2


def test_get_evidence_filters_by_promise(promise_store):
    promise_store.upsert_classification("P1", "E1", signal="kept", prompt_version="v1")
    promise_store.upsert_classification("P2", "E2", signal="kept", prompt_version="v1")
    assert set(promise_store.get_evidence("v1", promise_id="P2")) == {"P2"}


def test_get_evidence_empty_when_no_rows(promise_store):
    assert promise_store.get_evidence("v1") == {}


def test_get_signal_counts(promise_store):
    promise_store.upsert_classification("P", "E1", signal="kept", prompt_version="v1")
    promise_store.upsert_classification("P", "E2", signal="kept", prompt_version="v1")
    promise_store.upsert_classification("P", "E3", signal="reversal", prompt_version="v1")
    promise_store.upsert_classification("P", "E4", signal="none", prompt_version="v1")
    promise_store.upsert_classification("P", "E5", error="fail", prompt_version="v1")

    assert promise_store.get_signal_counts("P") == {"kept": 2, "reversal": 1, "none": 1}


# ---------------------------------------------------------------------------
# update_best_articles — sticky winner with strict-improvement rule
# ---------------------------------------------------------------------------


def test_update_best_inserts_when_no_prior(promise_store):
    promise_store.upsert_classification(
        "P", "E1", signal="kept", confidence=0.6, prompt_version="v1",
    )
    counts = promise_store.update_best_articles()
    assert counts == {"inserted": 1, "promoted": 0, "unchanged": 0, "dropped": 0}
    best = promise_store.get_best_article("P")
    assert best["article_entry_id"] == "E1"
    assert best["confidence"] == 0.6


def test_update_best_promotes_on_strictly_higher(promise_store):
    promise_store.upsert_classification("P", "E1", signal="kept", confidence=0.6, prompt_version="v1")
    promise_store.update_best_articles()
    promise_store.upsert_classification("P", "E2", signal="kept", confidence=0.9, prompt_version="v1")

    counts = promise_store.update_best_articles()
    assert counts == {"inserted": 0, "promoted": 1, "unchanged": 0, "dropped": 0}
    assert promise_store.get_best_article("P")["article_entry_id"] == "E2"


def test_update_best_keeps_on_tie(promise_store):
    """Equal confidence must NOT replace the incumbent."""
    promise_store.upsert_classification("P", "E1", signal="kept", confidence=0.8, prompt_version="v1")
    promise_store.update_best_articles()
    promise_store.upsert_classification("P", "E2", signal="kept", confidence=0.8, prompt_version="v1")

    counts = promise_store.update_best_articles()
    assert counts["promoted"] == 0
    assert promise_store.get_best_article("P")["article_entry_id"] == "E1"


def test_update_best_ignores_lower_reclassification(promise_store):
    """If the incumbent gets reclassified lower, it keeps the crown."""
    promise_store.upsert_classification("P", "E1", signal="kept", confidence=0.9, prompt_version="v1")
    promise_store.update_best_articles()
    # Same entry reclassified with lower confidence
    promise_store.upsert_classification("P", "E1", signal="step", confidence=0.4, prompt_version="v2")

    counts = promise_store.update_best_articles()
    assert counts["promoted"] == 0
    best = promise_store.get_best_article("P")
    assert best["article_entry_id"] == "E1"
    assert best["confidence"] == 0.9  # historical peak preserved


def test_update_best_drops_winner_reclassified_as_no_evidence(promise_store):
    """An article the classifier has dismissed must not keep heading the
    promise's row in the report."""
    promise_store.upsert_classification("P", "E1", signal="reversal", confidence=0.9, prompt_version="v1")
    promise_store.upsert_classification("P", "E2", signal="step", confidence=0.6, prompt_version="v1")
    promise_store.update_best_articles()
    assert promise_store.get_best_article("P")["article_entry_id"] == "E1"

    promise_store.upsert_classification("P", "E1", signal="none", confidence=0.9, prompt_version="v2")
    counts = promise_store.update_best_articles()
    assert counts["dropped"] == 1
    assert promise_store.get_best_article("P")["article_entry_id"] == "E2"


def test_update_best_drops_winner_with_no_evidence_left(promise_store):
    promise_store.upsert_classification("P", "E1", signal="kept", confidence=0.9, prompt_version="v1")
    promise_store.update_best_articles()
    promise_store.upsert_classification("P", "E1", signal="none", confidence=0.9, prompt_version="v2")

    counts = promise_store.update_best_articles()
    assert counts == {"inserted": 0, "promoted": 0, "unchanged": 0, "dropped": 1}
    assert promise_store.get_best_article("P") is None


def test_update_best_drops_winner_of_a_pre_signal_verdict(legacy_store):
    """Winners pinned by the old verdict prompt are not carried over."""
    with sqlite3.connect(legacy_store.db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS promise_best_article (
                promise_id TEXT PRIMARY KEY, article_entry_id TEXT NOT NULL,
                confidence REAL NOT NULL, captured_at TEXT DEFAULT (datetime('now')))
        """)
        conn.execute("INSERT OR REPLACE INTO promise_best_article "
                     "(promise_id, article_entry_id, confidence) VALUES ('P', 'BROKEN', 0.8)")
        conn.commit()
    assert legacy_store.update_best_articles()["dropped"] == 1
    assert legacy_store.get_best_article("P") is None


def test_update_best_excludes_no_signal_and_null_candidates(promise_store):
    promise_store.upsert_classification("P", "E1", signal="none", confidence=0.99, prompt_version="v1")
    promise_store.upsert_classification("P", "E2", error="boom", prompt_version="v1")
    promise_store.upsert_classification("P", "E3", signal="kept", confidence=0.5, prompt_version="v1")

    promise_store.update_best_articles()
    assert promise_store.get_best_article("P")["article_entry_id"] == "E3"


def test_update_best_per_promise_independent(promise_store):
    promise_store.upsert_classification("P1", "A", signal="kept", confidence=0.8, prompt_version="v1")
    promise_store.upsert_classification("P2", "B", signal="kept", confidence=0.4, prompt_version="v1")

    counts = promise_store.update_best_articles()
    assert counts["inserted"] == 2
    assert promise_store.get_best_article("P1")["article_entry_id"] == "A"
    assert promise_store.get_best_article("P2")["article_entry_id"] == "B"


def test_get_best_article_missing_returns_none(promise_store):
    assert promise_store.get_best_article("NONE") is None


# ---------------------------------------------------------------------------
# status changes: manual lock, source and article ids in the history
# ---------------------------------------------------------------------------


def test_manual_status_change_locks_the_promise(seeded_promises):
    seeded_promises.update_status("PROM-001", "kept", evidence="read the decree")
    promise = seeded_promises.get_promise("PROM-001")
    assert promise["current_status"] == "kept"
    assert promise["status_locked"] == 1
    assert seeded_promises.get_status_history("PROM-001")[-1]["source"] == "manual"


def test_manual_status_change_can_stay_unlocked(seeded_promises):
    seeded_promises.update_status("PROM-001", "made", lock=False)
    assert seeded_promises.get_promise("PROM-001")["status_locked"] == 0


def test_rollup_status_change_leaves_the_lock_alone(seeded_promises):
    seeded_promises.update_status("PROM-001", "in_progress", source="rollup")
    assert seeded_promises.get_promise("PROM-001")["status_locked"] == 0

    seeded_promises.update_status("PROM-002", "kept")  # manual: locks
    seeded_promises.update_status("PROM-002", "in_progress", source="rollup")
    assert seeded_promises.get_promise("PROM-002")["status_locked"] == 1


def test_status_history_records_article_ids(seeded_promises):
    seeded_promises.update_status(
        "PROM-001", "kept", evidence="llm-rollup: kept=2",
        article_ids=["E1", "E2"], source="rollup",
    )
    row = seeded_promises.get_status_history("PROM-001")[-1]
    assert row["article_ids"] == "E1,E2"
    assert row["source"] == "rollup"


def test_set_status_lock(seeded_promises):
    seeded_promises.update_status("PROM-001", "kept")
    seeded_promises.set_status_lock("PROM-001", False)
    assert seeded_promises.get_promise("PROM-001")["status_locked"] == 0
    with pytest.raises(ValueError):
        seeded_promises.set_status_lock("NOPE", True)


def test_review_flags_round_trip(seeded_promises):
    flags = ["review: reversal reported by 2 outlets", "delayed"]
    seeded_promises.set_review_flags("PROM-001", flags)
    assert seeded_promises.review_flags(seeded_promises.get_promise("PROM-001")) == flags

    seeded_promises.set_review_flags("PROM-001", [])
    promise = seeded_promises.get_promise("PROM-001")
    assert promise["review_flags"] is None
    assert seeded_promises.review_flags(promise) == []


# ---------------------------------------------------------------------------
# YAML sync: promise kind
# ---------------------------------------------------------------------------


def test_sync_from_yaml_stores_kind(promise_store, tmp_path):
    yaml_dir = tmp_path / "promises"
    yaml_dir.mkdir()
    (yaml_dir / "x.yaml").write_text(
        "promises:\n"
        "  - id: X-1\n    text: Megtartjuk.\n    category: gazdasag\n    kind: ongoing\n"
        "  - id: X-2\n    text: Létrehozzuk.\n    category: gazdasag\n",
        encoding="utf-8",
    )
    promise_store.sync_from_yaml(yaml_dir)
    assert promise_store.get_promise("X-1")["kind"] == "ongoing"
    assert promise_store.get_promise("X-2")["kind"] is None


def test_sync_from_yaml_keeps_status_and_lock(promise_store, tmp_path):
    yaml_dir = tmp_path / "promises"
    yaml_dir.mkdir()
    (yaml_dir / "x.yaml").write_text(
        "promises:\n  - id: X-1\n    text: Megtartjuk.\n    category: gazdasag\n",
        encoding="utf-8",
    )
    promise_store.sync_from_yaml(yaml_dir)
    promise_store.update_status("X-1", "kept")
    promise_store.sync_from_yaml(yaml_dir)

    promise = promise_store.get_promise("X-1")
    assert promise["current_status"] == "kept"
    assert promise["status_locked"] == 1
