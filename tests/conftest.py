"""Shared pytest fixtures for the tisza_tracker test suite."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict

import pytest

from tisza_tracker.core.promise_store import PromiseStore


@pytest.fixture
def tmp_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect runtime data (DBs, config) to an isolated tmpdir.

    Every code path in tisza_tracker that calls ``resolve_data_file`` honors
    the ``TISZA_TRACKER_DATA_DIR`` env var; setting it here makes PromiseStore
    (and DatabaseManager, ConfigManager) read/write inside ``tmp_path``.
    """
    monkeypatch.setenv("TISZA_TRACKER_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def promise_store(tmp_data_dir: Path) -> PromiseStore:
    """PromiseStore backed by a fresh promises.db under the tmp data dir."""
    config = {"database": {"promises_path": "promises.db"}}
    return PromiseStore(config)


@pytest.fixture
def seeded_promises(promise_store: PromiseStore) -> PromiseStore:
    """PromiseStore pre-populated with three promises across two categories."""
    for pid, text, category in [
        ("PROM-001", "First promise text", "gazdasag"),
        ("PROM-002", "Second promise text", "gazdasag"),
        ("PROM-003", "Third promise text", "oktatas"),
    ]:
        promise_store.add_promise(pid, text, category)
    return promise_store


# ---------------------------------------------------------------------------
# Helpers to build papers.db and history.db fixtures on demand
# ---------------------------------------------------------------------------

_PAPERS_SCHEMA = """
CREATE TABLE entries (
    id TEXT NOT NULL,
    topic TEXT NOT NULL,
    feed_name TEXT NOT NULL,
    title TEXT NOT NULL,
    link TEXT NOT NULL,
    summary TEXT,
    rank_score REAL,
    PRIMARY KEY (id, topic)
);
"""

_HISTORY_SCHEMA = """
CREATE TABLE matched_entries (
    entry_id TEXT PRIMARY KEY,
    feed_name TEXT NOT NULL,
    topics TEXT NOT NULL,
    title TEXT NOT NULL,
    link TEXT NOT NULL,
    summary TEXT
);
"""


@pytest.fixture
def papers_db(tmp_data_dir: Path) -> Path:
    """Empty papers.db at the conventional runtime location."""
    path = tmp_data_dir / "papers.db"
    conn = sqlite3.connect(path)
    conn.executescript(_PAPERS_SCHEMA)
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def history_db(tmp_data_dir: Path) -> Path:
    """Empty matched_entries_history.db."""
    path = tmp_data_dir / "matched_entries_history.db"
    conn = sqlite3.connect(path)
    conn.executescript(_HISTORY_SCHEMA)
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def insert_paper_entry():
    """Return a callable that inserts a row into a given papers.db."""
    def _insert(
        papers_path: Path,
        entry_id: str,
        title: str,
        link: str = "https://example.com/a",
        summary: str = "",
        topic: str = "gazdasag",
        feed_name: str = "telex",
    ) -> None:
        conn = sqlite3.connect(papers_path)
        try:
            conn.execute(
                "INSERT INTO entries (id, topic, feed_name, title, link, summary) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (entry_id, topic, feed_name, title, link, summary),
            )
            conn.commit()
        finally:
            conn.close()
    return _insert


@pytest.fixture
def insert_history_entry():
    """Return a callable that inserts a row into a given history DB."""
    def _insert(
        history_path: Path,
        entry_id: str,
        title: str,
        link: str = "https://example.com/a",
        summary: str = "",
        topics: str = "gazdasag",
        feed_name: str = "telex",
    ) -> None:
        conn = sqlite3.connect(history_path)
        try:
            conn.execute(
                "INSERT INTO matched_entries "
                "(entry_id, feed_name, topics, title, link, summary) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (entry_id, feed_name, topics, title, link, summary),
            )
            conn.commit()
        finally:
            conn.close()
    return _insert
