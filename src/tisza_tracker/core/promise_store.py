"""Promise database management.

Handles loading promise definitions from YAML files and tracking their status
in a SQLite database. Provides CRUD operations for promises, status transitions
with history logging, and article-to-promise linking.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .paths import resolve_data_file

logger = logging.getLogger(__name__)

VALID_STATUSES = (
    "made", "in_progress", "kept", "broken",
    "partially_kept", "abandoned", "modified",
)

# Per-article evidence signals (see processors.llm_classifier.to_signal) and
# the coarse label kept in the legacy ``verdict`` column for each of them.
SIGNAL_TO_VERDICT = {
    "kept": "kept",
    "partial": "kept",
    "step": "in_progress",
    "intent": "in_progress",
    "delay": "in_progress",
    "reversal": "broken",
    "none": "irrelevant",
}
SIGNALS = tuple(SIGNAL_TO_VERDICT)

# Strength of evidence, used to order a promise's articles in the report.
_EVIDENCE_RANK = {
    "kept": 6, "partial": 5, "reversal": 4, "step": 3, "delay": 2, "intent": 1,
}

# A failed LLM call is retried on later runs until it has been tried this often.
DEFAULT_MAX_ATTEMPTS = 3

# Columns added after the first release: (table, column, declaration).
_MIGRATIONS = (
    ("promises", "filter_pattern", "TEXT"),
    ("promises", "kind", "TEXT"),
    ("promises", "status_locked", "INTEGER DEFAULT 0"),
    ("promises", "review_flags", "TEXT"),
    ("promise_status_history", "source", "TEXT"),
    ("llm_classifications", "signal", "TEXT"),
    ("llm_classifications", "actor", "TEXT"),
    ("llm_classifications", "evidence_type", "TEXT"),
    ("llm_classifications", "scope", "TEXT"),
    ("llm_classifications", "event_date", "TEXT"),
    ("llm_classifications", "quote_verbatim", "INTEGER"),
    ("llm_classifications", "body_chars", "INTEGER"),
    ("llm_classifications", "outlet", "TEXT"),
    ("llm_classifications", "published_date", "TEXT"),
    ("llm_classifications", "attempts", "INTEGER DEFAULT 0"),
)


class PromiseStore:
    """Manages promise definitions and their runtime state in SQLite."""

    def __init__(self, config: Dict[str, Any]):
        db_cfg = config.get("database", {})
        db_path = db_cfg.get("promises_path", "promises.db")
        self.db_path = str(resolve_data_file(db_path, ensure_parent=True))
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS promises (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                text_en TEXT,
                source TEXT,
                source_url TEXT,
                date_made TEXT,
                category TEXT NOT NULL,
                subcategory TEXT,
                kind TEXT,
                deadline TEXT,
                keywords TEXT,
                ranking_query TEXT,
                filter_pattern TEXT,
                current_status TEXT DEFAULT 'made'
                    CHECK(current_status IN (
                        'made','in_progress','kept','broken',
                        'partially_kept','abandoned','modified'
                    )),
                status_updated TEXT,
                status_locked INTEGER DEFAULT 0,
                review_flags TEXT,
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS promise_status_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                promise_id TEXT NOT NULL REFERENCES promises(id),
                old_status TEXT,
                new_status TEXT NOT NULL,
                changed_at TEXT DEFAULT (datetime('now')),
                evidence TEXT,
                article_ids TEXT,
                source TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS promise_article_links (
                promise_id TEXT NOT NULL REFERENCES promises(id),
                article_entry_id TEXT NOT NULL,
                relevance_score REAL,
                linked_at TEXT DEFAULT (datetime('now')),
                link_type TEXT DEFAULT 'auto'
                    CHECK(link_type IN ('auto','manual')),
                PRIMARY KEY (promise_id, article_entry_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS llm_classifications (
                promise_id TEXT NOT NULL,
                article_entry_id TEXT NOT NULL,
                verdict TEXT
                    CHECK(verdict IN ('kept','in_progress','broken','irrelevant')),
                signal TEXT,
                confidence REAL,
                evidence_quote TEXT,
                quote_verbatim INTEGER,
                reasoning TEXT,
                actor TEXT,
                evidence_type TEXT,
                scope TEXT,
                event_date TEXT,
                outlet TEXT,
                published_date TEXT,
                body_chars INTEGER,
                model TEXT,
                prompt_version TEXT,
                pass1_relevant INTEGER,
                pass1_confidence REAL,
                error TEXT,
                attempts INTEGER DEFAULT 0,
                classified_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (promise_id, article_entry_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS promise_best_article (
                promise_id TEXT PRIMARY KEY REFERENCES promises(id),
                article_entry_id TEXT NOT NULL,
                confidence REAL NOT NULL,
                captured_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # Lightweight migration: add columns missing from older databases
        for table, column, declaration in _MIGRATIONS:
            cursor.execute(f"PRAGMA table_info({table})")
            if column in {row[1] for row in cursor.fetchall()}:
                continue
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
            except Exception as e:
                logger.debug("Column %s.%s may already exist: %s", table, column, e)

        # Rows written before signals existed: a gate rejection carries none.
        cursor.execute(
            "UPDATE llm_classifications SET signal = 'none' "
            "WHERE signal IS NULL AND verdict = 'irrelevant'"
        )

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_promises_category
            ON promises(category)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_promises_status
            ON promises(current_status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_promise_links_promise
            ON promise_article_links(promise_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_promise_links_article
            ON promise_article_links(article_entry_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_llm_verdict
            ON llm_classifications(verdict)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_llm_promise
            ON llm_classifications(promise_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_llm_signal
            ON llm_classifications(signal)
        """)

        conn.commit()
        conn.close()

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ---- YAML sync ----

    def sync_from_yaml(self, yaml_dir: Path) -> Dict[str, int]:
        """Idempotent upsert from YAML promise files into SQLite.

        Returns counts: {"created": N, "updated": N, "total": N}
        """
        if not yaml_dir.exists():
            logger.warning("Promise YAML directory does not exist: %s", yaml_dir)
            return {"created": 0, "updated": 0, "total": 0}

        created = 0
        updated = 0
        for yaml_file in sorted(yaml_dir.glob("*.yaml")) + sorted(yaml_dir.glob("*.yml")):
            with open(yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not data or not isinstance(data.get("promises"), list):
                continue
            for p in data["promises"]:
                pid = p.get("id")
                if not pid:
                    continue
                existed = self.get_promise(pid) is not None
                self._upsert_promise(p)
                if existed:
                    updated += 1
                else:
                    created += 1

        total = created + updated
        logger.info("Promise sync: %d created, %d updated, %d total", created, updated, total)
        return {"created": created, "updated": updated, "total": total}

    def _upsert_promise(self, p: Dict[str, Any]) -> None:
        keywords = p.get("keywords")
        if isinstance(keywords, list):
            keywords = ", ".join(keywords)

        with self._connection() as conn:
            conn.execute("""
                INSERT INTO promises (id, text, text_en, source, source_url,
                    date_made, category, subcategory, kind, deadline, keywords,
                    ranking_query, filter_pattern, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    text = excluded.text,
                    text_en = excluded.text_en,
                    source = excluded.source,
                    source_url = excluded.source_url,
                    date_made = excluded.date_made,
                    category = excluded.category,
                    subcategory = excluded.subcategory,
                    kind = excluded.kind,
                    deadline = excluded.deadline,
                    keywords = excluded.keywords,
                    ranking_query = excluded.ranking_query,
                    filter_pattern = excluded.filter_pattern,
                    notes = COALESCE(promises.notes, excluded.notes),
                    updated_at = datetime('now')
            """, (
                p["id"], p["text"], p.get("text_en"), p.get("source"),
                p.get("source_url"), p.get("date_made"), p.get("category", ""),
                p.get("subcategory"), p.get("kind"), p.get("deadline"), keywords,
                p.get("ranking_query"), p.get("filter_pattern"), p.get("notes"),
            ))

    # ---- CRUD ----

    def get_promise(self, promise_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM promises WHERE id = ?", (promise_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_promises(
        self,
        category: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM promises WHERE 1=1"
        params: list = []
        if category:
            query += " AND category = ?"
            params.append(category)
        if status:
            query += " AND current_status = ?"
            params.append(status)
        query += " ORDER BY category, id"

        with self._connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def add_promise(self, promise_id: str, text: str, category: str,
                    source: Optional[str] = None, **kwargs: Any) -> None:
        p = {"id": promise_id, "text": text, "category": category,
             "source": source, **kwargs}
        self._upsert_promise(p)
        logger.info("Added promise %s", promise_id)

    # ---- Status tracking ----

    def update_status(
        self,
        promise_id: str,
        new_status: str,
        evidence: Optional[str] = None,
        article_ids: Optional[List[str]] = None,
        *,
        source: str = "manual",
        lock: Optional[bool] = None,
    ) -> None:
        """Change a promise's status and log the transition.

        A ``manual`` change locks the status so the automatic rollup leaves it
        alone (pass ``lock=False`` to keep it unlocked); a ``rollup`` change
        never touches the lock.
        """
        if new_status not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{new_status}'. Must be one of: {VALID_STATUSES}")
        if lock is None:
            lock = True if source == "manual" else None

        with self._connection() as conn:
            row = conn.execute(
                "SELECT current_status FROM promises WHERE id = ?", (promise_id,)
            ).fetchone()
            if not row:
                raise ValueError(f"Promise '{promise_id}' not found")

            old_status = row["current_status"]
            article_ids_str = ",".join(article_ids) if article_ids else None

            conn.execute("""
                INSERT INTO promise_status_history
                    (promise_id, old_status, new_status, evidence, article_ids, source)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (promise_id, old_status, new_status, evidence, article_ids_str, source))

            conn.execute("""
                UPDATE promises
                SET current_status = ?, status_updated = datetime('now'),
                    status_locked = COALESCE(?, status_locked),
                    updated_at = datetime('now')
                WHERE id = ?
            """, (new_status, None if lock is None else int(lock), promise_id))

        logger.info("Promise %s: %s -> %s (%s)", promise_id, old_status, new_status, source)

    def set_status_lock(self, promise_id: str, locked: bool) -> None:
        """Lock or unlock a promise's status against the automatic rollup."""
        with self._connection() as conn:
            cur = conn.execute(
                "UPDATE promises SET status_locked = ?, updated_at = datetime('now') "
                "WHERE id = ?",
                (int(locked), promise_id),
            )
            if cur.rowcount == 0:
                raise ValueError(f"Promise '{promise_id}' not found")

    def set_review_flags(self, promise_id: str, flags: List[str]) -> None:
        """Replace the rollup's flags for a promise (empty list clears them)."""
        value = json.dumps(flags, ensure_ascii=False) if flags else None
        with self._connection() as conn:
            conn.execute(
                "UPDATE promises SET review_flags = ? "
                "WHERE id = ? AND review_flags IS NOT ?",
                (value, promise_id, value),
            )

    @staticmethod
    def review_flags(promise: Dict[str, Any]) -> List[str]:
        """Decode the ``review_flags`` column of a promise row."""
        raw = promise.get("review_flags")
        if not raw:
            return []
        try:
            flags = json.loads(raw)
        except (TypeError, ValueError):
            return []
        return [str(f) for f in flags] if isinstance(flags, list) else []

    def get_status_history(self, promise_id: str) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM promise_status_history WHERE promise_id = ? ORDER BY changed_at",
                (promise_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ---- Article linking ----

    def link_article(
        self,
        promise_id: str,
        article_entry_id: str,
        relevance_score: float = 0.0,
        link_type: str = "auto",
    ) -> None:
        with self._connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO promise_article_links
                    (promise_id, article_entry_id, relevance_score, link_type)
                VALUES (?, ?, ?, ?)
            """, (promise_id, article_entry_id, relevance_score, link_type))

    def get_linked_articles(self, promise_id: str) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM promise_article_links WHERE promise_id = ? ORDER BY relevance_score DESC",
                (promise_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_promises_for_article(self, article_entry_id: str) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute("""
                SELECT p.*, pal.relevance_score, pal.link_type
                FROM promises p
                JOIN promise_article_links pal ON p.id = pal.promise_id
                WHERE pal.article_entry_id = ?
                ORDER BY pal.relevance_score DESC
            """, (article_entry_id,)).fetchall()
            return [dict(r) for r in rows]

    # ---- LLM classifications ----

    def upsert_classification(
        self,
        promise_id: str,
        article_entry_id: str,
        *,
        signal: Optional[str] = None,
        verdict: Optional[str] = None,
        confidence: Optional[float] = None,
        evidence_quote: Optional[str] = None,
        quote_verbatim: Optional[bool] = None,
        reasoning: Optional[str] = None,
        actor: Optional[str] = None,
        evidence_type: Optional[str] = None,
        scope: Optional[str] = None,
        event_date: Optional[str] = None,
        outlet: Optional[str] = None,
        published_date: Optional[str] = None,
        body_chars: Optional[int] = None,
        model: Optional[str] = None,
        prompt_version: Optional[str] = None,
        pass1_relevant: Optional[bool] = None,
        pass1_confidence: Optional[float] = None,
        error: Optional[str] = None,
    ) -> None:
        """Insert or replace the classification of one promise-article link.

        ``attempts`` counts classifications under the same ``prompt_version``
        so that failed rows are retried a bounded number of times.
        """
        if verdict is None and signal is not None:
            verdict = SIGNAL_TO_VERDICT.get(signal)

        def flag(value: Optional[bool]) -> Optional[int]:
            return int(value) if value is not None else None

        with self._connection() as conn:
            conn.execute("""
                INSERT INTO llm_classifications (
                    promise_id, article_entry_id, verdict, signal, confidence,
                    evidence_quote, quote_verbatim, reasoning, actor,
                    evidence_type, scope, event_date, outlet, published_date,
                    body_chars, model, prompt_version, pass1_relevant,
                    pass1_confidence, error, attempts, classified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          1, datetime('now'))
                ON CONFLICT(promise_id, article_entry_id) DO UPDATE SET
                    attempts = CASE
                        WHEN llm_classifications.prompt_version IS excluded.prompt_version
                        THEN COALESCE(llm_classifications.attempts, 0) + 1
                        ELSE 1 END,
                    verdict = excluded.verdict,
                    signal = excluded.signal,
                    confidence = excluded.confidence,
                    evidence_quote = excluded.evidence_quote,
                    quote_verbatim = excluded.quote_verbatim,
                    reasoning = excluded.reasoning,
                    actor = excluded.actor,
                    evidence_type = excluded.evidence_type,
                    scope = excluded.scope,
                    event_date = excluded.event_date,
                    outlet = excluded.outlet,
                    published_date = excluded.published_date,
                    body_chars = excluded.body_chars,
                    model = excluded.model,
                    prompt_version = excluded.prompt_version,
                    pass1_relevant = excluded.pass1_relevant,
                    pass1_confidence = excluded.pass1_confidence,
                    error = excluded.error,
                    classified_at = datetime('now')
            """, (
                promise_id, article_entry_id, verdict, signal, confidence,
                evidence_quote, flag(quote_verbatim), reasoning, actor,
                evidence_type, scope, event_date, outlet, published_date,
                body_chars, model, prompt_version, flag(pass1_relevant),
                pass1_confidence, error,
            ))

    def get_classification(
        self, promise_id: str, article_entry_id: str,
    ) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM llm_classifications WHERE promise_id = ? AND article_entry_id = ?",
                (promise_id, article_entry_id),
            ).fetchone()
            return dict(row) if row else None

    def list_unclassified_links(
        self,
        prompt_version: str,
        max_per_promise: Optional[int] = None,
        *,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        force: bool = False,
    ) -> List[Dict[str, Any]]:
        """Return promise_article_links that still need classifying.

        A link qualifies if

        * it has no classification row, or
        * the stored row has a different prompt_version (stale cache), unless
          the relevance gate rejected the article: ``prompt_version`` covers
          the extraction pass, so gate rejections stay valid, or
        * the last attempt failed and fewer than *max_attempts* were made.

        With *force* every link qualifies.  Results are ordered by promise_id,
        descending relevance_score.

        ``lc.prompt_version IS NOT ?`` is NULL-safe: it is TRUE when the stored
        value is NULL *or* differs from ``prompt_version``.
        """
        with self._connection() as conn:
            rows = conn.execute("""
                SELECT pal.promise_id,
                       pal.article_entry_id,
                       pal.relevance_score
                FROM promise_article_links pal
                LEFT JOIN llm_classifications lc
                  ON lc.promise_id = pal.promise_id
                 AND lc.article_entry_id = pal.article_entry_id
                WHERE ?
                   OR lc.promise_id IS NULL
                   OR (lc.error IS NOT NULL AND COALESCE(lc.attempts, 0) < ?)
                   OR (lc.error IS NULL
                       AND lc.prompt_version IS NOT ?
                       AND lc.pass1_relevant IS NOT 0)
                   OR (lc.error IS NOT NULL AND lc.prompt_version IS NOT ?)
                ORDER BY pal.promise_id, pal.relevance_score DESC
            """, (int(force), max_attempts, prompt_version, prompt_version)).fetchall()
            links = [dict(r) for r in rows]

        if max_per_promise is None:
            return links

        trimmed: List[Dict[str, Any]] = []
        counts: Dict[str, int] = {}
        for link in links:
            pid = link["promise_id"]
            if counts.get(pid, 0) >= max_per_promise:
                continue
            counts[pid] = counts.get(pid, 0) + 1
            trimmed.append(link)
        return trimmed

    def get_signal_counts(self, promise_id: str) -> Dict[str, int]:
        with self._connection() as conn:
            rows = conn.execute("""
                SELECT signal, COUNT(*) AS cnt
                FROM llm_classifications
                WHERE promise_id = ? AND signal IS NOT NULL
                GROUP BY signal
            """, (promise_id,)).fetchall()
            return {r["signal"]: r["cnt"] for r in rows}

    def get_evidence(
        self,
        prompt_version: Optional[str] = None,
        promise_id: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Group signal-bearing classifications by promise_id.

        Only rows that carry a signal other than ``none`` are evidence.  When
        *prompt_version* is given, rows extracted under another version are
        left out, so verdicts of a superseded prompt never reach the rollup.
        One DB query total.
        """
        query = """
            SELECT promise_id, article_entry_id, signal, outlet,
                   published_date AS published, confidence, evidence_quote,
                   quote_verbatim, reasoning, body_chars, classified_at
            FROM llm_classifications
            WHERE signal IS NOT NULL AND signal != 'none' AND error IS NULL
        """
        params: list = []
        if prompt_version is not None:
            query += " AND prompt_version IS ?"
            params.append(prompt_version)
        if promise_id is not None:
            query += " AND promise_id = ?"
            params.append(promise_id)
        query += " ORDER BY promise_id, published_date, article_entry_id"

        with self._connection() as conn:
            rows = conn.execute(query, params).fetchall()

        groups: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            groups.setdefault(r["promise_id"], []).append(dict(r))
        return groups

    # ---- Sticky best article per promise ----

    def update_best_articles(self) -> Dict[str, int]:
        """Pin the highest-confidence piece of evidence per promise.

        For each promise, finds the current argmax of ``confidence`` over
        classifications that carry a signal other than ``none``.  The stored
        row in ``promise_best_article`` is replaced **only if** the new
        candidate's confidence is strictly greater than the stored value — ties
        keep the existing champion, and a champion's later re-classification to
        a lower confidence does not demote it.

        A champion is dropped when its article no longer counts as evidence
        (re-classified to ``none``, or never extracted under the signal
        scheme), so an article the classifier has dismissed cannot keep
        heading the promise's row in the report.

        Returns counts: ``{"inserted": N, "promoted": N, "unchanged": N,
        "dropped": N}``.
        """
        inserted = 0
        promoted = 0
        unchanged = 0

        with self._connection() as conn:
            dropped = conn.execute("""
                DELETE FROM promise_best_article
                WHERE NOT EXISTS (
                    SELECT 1 FROM llm_classifications lc
                    WHERE lc.promise_id = promise_best_article.promise_id
                      AND lc.article_entry_id = promise_best_article.article_entry_id
                      AND lc.signal IS NOT NULL
                      AND lc.signal != 'none'
                )
            """).rowcount

            candidates = conn.execute("""
                SELECT promise_id,
                       article_entry_id,
                       confidence
                FROM llm_classifications
                WHERE signal IS NOT NULL
                  AND signal != 'none'
                  AND confidence IS NOT NULL
                  AND (promise_id, confidence) IN (
                      SELECT promise_id, MAX(confidence)
                      FROM llm_classifications
                      WHERE signal IS NOT NULL
                        AND signal != 'none'
                        AND confidence IS NOT NULL
                      GROUP BY promise_id
                  )
                GROUP BY promise_id
            """).fetchall()

            for row in candidates:
                pid = row["promise_id"]
                eid = row["article_entry_id"]
                conf = float(row["confidence"])

                existing = conn.execute(
                    "SELECT article_entry_id, confidence FROM promise_best_article "
                    "WHERE promise_id = ?",
                    (pid,),
                ).fetchone()

                if existing is None:
                    conn.execute(
                        "INSERT INTO promise_best_article "
                        "(promise_id, article_entry_id, confidence) VALUES (?, ?, ?)",
                        (pid, eid, conf),
                    )
                    inserted += 1
                elif conf > float(existing["confidence"]):
                    conn.execute(
                        "UPDATE promise_best_article "
                        "SET article_entry_id = ?, confidence = ?, "
                        "    captured_at = datetime('now') "
                        "WHERE promise_id = ?",
                        (eid, conf, pid),
                    )
                    promoted += 1
                else:
                    unchanged += 1

        return {
            "inserted": inserted, "promoted": promoted,
            "unchanged": unchanged, "dropped": dropped,
        }

    def get_best_article(self, promise_id: str) -> Optional[Dict[str, Any]]:
        """Return the sticky winner row for *promise_id*, or None."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM promise_best_article WHERE promise_id = ?",
                (promise_id,),
            ).fetchone()
            return dict(row) if row else None

    # ---- Enriched queries ----

    def get_promises_with_articles(
        self,
        papers_db_path: str,
        history_db_path: Optional[str] = None,
        all_feeds_db_path: Optional[str] = None,
        category: Optional[str] = None,
        max_per_promise: Optional[int] = None,
        drop_irrelevant: bool = True,
    ) -> List[Dict[str, Any]]:
        """Return all promises with their linked articles enriched with title/link.

        Resolves each ``promise_article_links`` row's entry_id into a
        title/link by walking three sources in priority order: papers.db
        (current run) → matched_entries_history.db (long-term archive) →
        all_feed_entries.db (RSS dedup archive).  The third source is the
        last-resort fallback that prevents an article from disappearing from
        the report once papers.db has been rotated and if the topic config
        never enabled archiving.

        Each article dict contains: title, link, relevance_score, entry_id,
        and the LLM classification fields (signal, verdict, confidence,
        evidence_quote) if a row exists in ``llm_classifications``.  The
        evidence quote is only passed on when it was found verbatim in the
        article.

        When ``drop_irrelevant`` is True (default), articles that carry no
        evidence (signal ``'none'``) are excluded.

        When ``max_per_promise`` is set, only the top-N articles per promise
        are kept, ranked by strength of evidence, then LLM confidence
        (descending, NULLs last), then relevance_score.  The sticky winner (if
        any) is always placed first and counts against the top-N quota.
        """
        with self._connection() as conn:
            conn.execute("ATTACH ? AS papers", (papers_db_path,))
            if history_db_path:
                conn.execute("ATTACH ? AS history", (history_db_path,))
            if all_feeds_db_path:
                conn.execute("ATTACH ? AS feeds", (all_feeds_db_path,))
            try:
                best_map: Dict[str, str] = {
                    r["promise_id"]: r["article_entry_id"]
                    for r in conn.execute(
                        "SELECT promise_id, article_entry_id FROM promise_best_article"
                    ).fetchall()
                }

                query = "SELECT * FROM promises WHERE 1=1"
                params: list = []
                if category:
                    query += " AND category = ?"
                    params.append(category)
                query += " ORDER BY category, id"
                promises = [dict(r) for r in conn.execute(query, params).fetchall()]

                for promise in promises:
                    link_rows = conn.execute("""
                        SELECT pal.article_entry_id AS entry_id,
                               pal.relevance_score,
                               lc.signal, lc.verdict, lc.confidence,
                               lc.evidence_quote, lc.quote_verbatim
                        FROM promise_article_links pal
                        LEFT JOIN llm_classifications lc
                          ON lc.promise_id = pal.promise_id
                         AND lc.article_entry_id = pal.article_entry_id
                        WHERE pal.promise_id = ?
                    """, (promise["id"],)).fetchall()

                    if not link_rows:
                        promise["articles"] = []
                        continue

                    ids = [r["entry_id"] for r in link_rows]
                    placeholders = ",".join("?" for _ in ids)

                    # papers.entries has PK (id, topic), so an entry may
                    # appear under multiple topics; setdefault keeps one.
                    resolved: Dict[str, tuple] = {}
                    for r in conn.execute(
                        f"SELECT id, title, link FROM papers.entries "
                        f"WHERE id IN ({placeholders})",
                        ids,
                    ).fetchall():
                        resolved.setdefault(r["id"], (r["title"], r["link"]))

                    if history_db_path:
                        missing = [eid for eid in ids if eid not in resolved]
                        if missing:
                            ph = ",".join("?" for _ in missing)
                            for r in conn.execute(
                                f"SELECT entry_id, title, link "
                                f"FROM history.matched_entries "
                                f"WHERE entry_id IN ({ph})",
                                missing,
                            ).fetchall():
                                resolved[r["entry_id"]] = (r["title"], r["link"])

                    if all_feeds_db_path:
                        missing = [eid for eid in ids if eid not in resolved]
                        if missing:
                            ph = ",".join("?" for _ in missing)
                            for r in conn.execute(
                                f"SELECT entry_id, title, link "
                                f"FROM feeds.feed_entries "
                                f"WHERE entry_id IN ({ph})",
                                missing,
                            ).fetchall():
                                resolved[r["entry_id"]] = (r["title"], r["link"])

                    articles: List[Dict[str, Any]] = []
                    for r in link_rows:
                        eid = r["entry_id"]
                        title_link = resolved.get(eid)
                        if title_link is None:
                            continue
                        title, link = title_link
                        articles.append({
                            "title": title,
                            "link": link,
                            "relevance_score": r["relevance_score"],
                            "entry_id": eid,
                            "signal": r["signal"],
                            "verdict": r["verdict"],
                            "confidence": r["confidence"],
                            "evidence_quote": (
                                r["evidence_quote"] if r["quote_verbatim"] else None
                            ),
                        })

                    sticky_eid = best_map.get(promise["id"])

                    if drop_irrelevant:
                        articles = [
                            a for a in articles
                            if a.get("signal") != "none"
                            and a.get("verdict") != "irrelevant"
                        ]

                    articles.sort(
                        key=lambda a: (
                            _EVIDENCE_RANK.get(a.get("signal") or "", 0),
                            a.get("confidence") if a.get("confidence") is not None else -1.0,
                            a.get("relevance_score") or 0,
                        ),
                        reverse=True,
                    )

                    if sticky_eid:
                        sticky_idx = next(
                            (i for i, a in enumerate(articles)
                             if a.get("entry_id") == sticky_eid),
                            None,
                        )
                        if sticky_idx is not None and sticky_idx != 0:
                            articles.insert(0, articles.pop(sticky_idx))

                    if max_per_promise is not None:
                        articles = articles[:max_per_promise]

                    promise["articles"] = articles
            finally:
                if all_feeds_db_path:
                    conn.execute("DETACH feeds")
                if history_db_path:
                    conn.execute("DETACH history")
                conn.execute("DETACH papers")
        return promises

    # ---- Statistics ----

    def get_stats(self) -> Dict[str, Any]:
        with self._connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM promises").fetchone()[0]

            status_rows = conn.execute(
                "SELECT current_status, COUNT(*) as cnt FROM promises GROUP BY current_status"
            ).fetchall()
            by_status = {r["current_status"]: r["cnt"] for r in status_rows}

            cat_rows = conn.execute(
                "SELECT category, COUNT(*) as cnt FROM promises GROUP BY category"
            ).fetchall()
            by_category = {r["category"]: r["cnt"] for r in cat_rows}

            links = conn.execute("SELECT COUNT(*) FROM promise_article_links").fetchone()[0]

        return {
            "total_promises": total,
            "by_status": by_status,
            "by_category": by_category,
            "total_article_links": links,
        }
