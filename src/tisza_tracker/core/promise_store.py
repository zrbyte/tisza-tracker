"""Promise database management.

Handles loading promise definitions from YAML files and tracking their status
in a SQLite database. Provides CRUD operations for promises, status transitions
with history logging, and article-to-promise linking.
"""

from __future__ import annotations

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
                article_ids TEXT
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
                confidence REAL,
                evidence_quote TEXT,
                reasoning TEXT,
                model TEXT,
                prompt_version TEXT,
                pass1_relevant INTEGER,
                pass1_confidence REAL,
                error TEXT,
                classified_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (promise_id, article_entry_id)
            )
        """)

        # Lightweight migration: add filter_pattern if missing
        cursor.execute("PRAGMA table_info(promises)")
        columns = {row[1] for row in cursor.fetchall()}
        if 'filter_pattern' not in columns:
            try:
                cursor.execute("ALTER TABLE promises ADD COLUMN filter_pattern TEXT")
            except Exception as e:
                logger.debug("Column filter_pattern may already exist: %s", e)

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
                    date_made, category, subcategory, deadline, keywords,
                    ranking_query, filter_pattern, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    text = excluded.text,
                    text_en = excluded.text_en,
                    source = excluded.source,
                    source_url = excluded.source_url,
                    date_made = excluded.date_made,
                    category = excluded.category,
                    subcategory = excluded.subcategory,
                    deadline = excluded.deadline,
                    keywords = excluded.keywords,
                    ranking_query = excluded.ranking_query,
                    filter_pattern = excluded.filter_pattern,
                    notes = COALESCE(promises.notes, excluded.notes),
                    updated_at = datetime('now')
            """, (
                p["id"], p["text"], p.get("text_en"), p.get("source"),
                p.get("source_url"), p.get("date_made"), p.get("category", ""),
                p.get("subcategory"), p.get("deadline"), keywords,
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
    ) -> None:
        if new_status not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{new_status}'. Must be one of: {VALID_STATUSES}")

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
                    (promise_id, old_status, new_status, evidence, article_ids)
                VALUES (?, ?, ?, ?, ?)
            """, (promise_id, old_status, new_status, evidence, article_ids_str))

            conn.execute("""
                UPDATE promises
                SET current_status = ?, status_updated = datetime('now'),
                    updated_at = datetime('now')
                WHERE id = ?
            """, (new_status, promise_id))

        logger.info("Promise %s: %s -> %s", promise_id, old_status, new_status)

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
        verdict: Optional[str] = None,
        confidence: Optional[float] = None,
        evidence_quote: Optional[str] = None,
        reasoning: Optional[str] = None,
        model: Optional[str] = None,
        prompt_version: Optional[str] = None,
        pass1_relevant: Optional[bool] = None,
        pass1_confidence: Optional[float] = None,
        error: Optional[str] = None,
    ) -> None:
        with self._connection() as conn:
            conn.execute("""
                INSERT INTO llm_classifications (
                    promise_id, article_entry_id, verdict, confidence,
                    evidence_quote, reasoning, model, prompt_version,
                    pass1_relevant, pass1_confidence, error, classified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(promise_id, article_entry_id) DO UPDATE SET
                    verdict = excluded.verdict,
                    confidence = excluded.confidence,
                    evidence_quote = excluded.evidence_quote,
                    reasoning = excluded.reasoning,
                    model = excluded.model,
                    prompt_version = excluded.prompt_version,
                    pass1_relevant = excluded.pass1_relevant,
                    pass1_confidence = excluded.pass1_confidence,
                    error = excluded.error,
                    classified_at = datetime('now')
            """, (
                promise_id, article_entry_id, verdict, confidence,
                evidence_quote, reasoning, model, prompt_version,
                int(pass1_relevant) if pass1_relevant is not None else None,
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
    ) -> List[Dict[str, Any]]:
        """Return promise_article_links lacking a current-version classification.

        A link qualifies if it has no classification row OR the stored row has
        a different prompt_version (stale cache).  Results are ordered by
        promise_id, descending relevance_score.
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
                WHERE lc.promise_id IS NULL
                   OR lc.prompt_version IS NOT ?
                   OR lc.prompt_version != ?
                ORDER BY pal.promise_id, pal.relevance_score DESC
            """, (prompt_version, prompt_version)).fetchall()
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

    def get_verdict_counts(self, promise_id: str) -> Dict[str, int]:
        with self._connection() as conn:
            rows = conn.execute("""
                SELECT verdict, COUNT(*) AS cnt
                FROM llm_classifications
                WHERE promise_id = ? AND verdict IS NOT NULL
                GROUP BY verdict
            """, (promise_id,)).fetchall()
            return {r["verdict"]: r["cnt"] for r in rows}

    # ---- Enriched queries ----

    def get_promises_with_articles(
        self,
        papers_db_path: str,
        history_db_path: Optional[str] = None,
        category: Optional[str] = None,
        max_per_promise: Optional[int] = None,
        drop_irrelevant: bool = True,
    ) -> List[Dict[str, Any]]:
        """Return all promises with their linked articles enriched with title/link.

        Attaches the papers database (current run) and optionally the history
        database to resolve article entry IDs into human-readable titles and
        URLs.  Articles found in papers.db take precedence; any remaining
        unresolved links are looked up in matched_entries_history.db.

        Each article dict contains: title, link, relevance_score, and if an
        LLM classification exists: verdict, confidence, evidence_quote.

        When ``drop_irrelevant`` is True (default), articles whose LLM verdict
        is ``'irrelevant'`` are excluded.  Articles with no classification row
        pass through unchanged.

        When ``max_per_promise`` is set, only the top-N articles per promise
        are kept, ranked by LLM confidence (descending, NULLs last) then by
        relevance_score.
        """
        with self._connection() as conn:
            conn.execute("ATTACH ? AS papers", (papers_db_path,))
            if history_db_path:
                conn.execute("ATTACH ? AS history", (history_db_path,))
            try:
                query = "SELECT * FROM promises WHERE 1=1"
                params: list = []
                if category:
                    query += " AND category = ?"
                    params.append(category)
                query += " ORDER BY category, id"
                promises = [dict(r) for r in conn.execute(query, params).fetchall()]

                for promise in promises:
                    rows = conn.execute("""
                        SELECT DISTINCT e.title, e.link, pal.relevance_score,
                               pal.article_entry_id AS entry_id,
                               lc.verdict, lc.confidence, lc.evidence_quote
                        FROM promise_article_links pal
                        JOIN papers.entries e ON pal.article_entry_id = e.id
                        LEFT JOIN llm_classifications lc
                          ON lc.promise_id = pal.promise_id
                         AND lc.article_entry_id = pal.article_entry_id
                        WHERE pal.promise_id = ?
                    """, (promise["id"],)).fetchall()
                    articles = [dict(r) for r in rows]
                    resolved_ids = {a["entry_id"] for a in articles}

                    if history_db_path:
                        if resolved_ids:
                            placeholders = ",".join("?" for _ in resolved_ids)
                            hist_rows = conn.execute(f"""
                                SELECT DISTINCT h.title, h.link, pal.relevance_score,
                                       pal.article_entry_id AS entry_id,
                                       lc.verdict, lc.confidence, lc.evidence_quote
                                FROM promise_article_links pal
                                JOIN history.matched_entries h
                                    ON pal.article_entry_id = h.entry_id
                                LEFT JOIN llm_classifications lc
                                  ON lc.promise_id = pal.promise_id
                                 AND lc.article_entry_id = pal.article_entry_id
                                WHERE pal.promise_id = ?
                                  AND pal.article_entry_id NOT IN ({placeholders})
                            """, (promise["id"], *resolved_ids)).fetchall()
                        else:
                            hist_rows = conn.execute("""
                                SELECT DISTINCT h.title, h.link, pal.relevance_score,
                                       pal.article_entry_id AS entry_id,
                                       lc.verdict, lc.confidence, lc.evidence_quote
                                FROM promise_article_links pal
                                JOIN history.matched_entries h
                                    ON pal.article_entry_id = h.entry_id
                                LEFT JOIN llm_classifications lc
                                  ON lc.promise_id = pal.promise_id
                                 AND lc.article_entry_id = pal.article_entry_id
                                WHERE pal.promise_id = ?
                            """, (promise["id"],)).fetchall()
                        articles.extend(dict(r) for r in hist_rows)

                    if drop_irrelevant:
                        articles = [a for a in articles if a.get("verdict") != "irrelevant"]

                    # Sort: LLM confidence first (None treated as -1), then score
                    articles.sort(
                        key=lambda a: (
                            a.get("confidence") if a.get("confidence") is not None else -1.0,
                            a.get("relevance_score") or 0,
                        ),
                        reverse=True,
                    )

                    if max_per_promise is not None:
                        articles = articles[:max_per_promise]

                    promise["articles"] = articles
            finally:
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
