"""Tests for the classify command: rollup, article resolution, end-to-end run."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tisza_tracker.commands import classify as classify_cmd
from tisza_tracker.commands.classify import (
    _format_evidence,
    _load_llm_config,
    _maybe_rollup,
    _resolve_article,
)
from tisza_tracker.processors.llm_classifier import effective_prompt_version


LLM_CFG = {"prompt_version": "v1", "rollup": {"enabled": True}}
VERSION = effective_prompt_version(LLM_CFG)
TODAY = date(2026, 10, 9)


def add_evidence(ps, pid, eid, signal, outlet="Telex", published="2026-06-10",
                 version=VERSION, **extra):
    """Link an article to a promise and store its classification."""
    ps.link_article(pid, eid, relevance_score=0.5)
    ps.upsert_classification(
        pid, eid, signal=signal, confidence=0.9, outlet=outlet,
        published_date=published, pass1_relevant=signal != "none" or None,
        prompt_version=version, **extra,
    )


def rollup(ps, cfg=LLM_CFG, **kwargs):
    kwargs.setdefault("today", TODAY)
    _maybe_rollup(ps, cfg, skip=False, **kwargs)


def status_of(ps, pid):
    return ps.get_promise(pid)["current_status"]


def flags_of(ps, pid):
    return ps.review_flags(ps.get_promise(pid))


# ---------------------------------------------------------------------------
# Rollup: evidence → status
# ---------------------------------------------------------------------------


def test_rollup_full_pipeline(promise_store):
    """Seed classifications, run the rollup, verify each status."""
    ps = promise_store
    for pid in ("P-KEPT", "P-PARTIAL", "P-STEP", "P-TALK", "P-NOISE", "P-EMPTY"):
        ps.add_promise(pid, pid, "gazdasag")

    add_evidence(ps, "P-KEPT", "K1", "kept", "Telex")
    add_evidence(ps, "P-KEPT", "K2", "kept", "HVG")
    add_evidence(ps, "P-PARTIAL", "A1", "partial", "Telex")
    add_evidence(ps, "P-PARTIAL", "A2", "kept", "HVG")
    add_evidence(ps, "P-STEP", "S1", "step")
    add_evidence(ps, "P-TALK", "T1", "intent")
    add_evidence(ps, "P-NOISE", "N1", "none")

    rollup(ps)

    assert status_of(ps, "P-KEPT") == "kept"
    assert status_of(ps, "P-PARTIAL") == "partially_kept"
    assert status_of(ps, "P-STEP") == "in_progress"
    assert status_of(ps, "P-TALK") == "made"
    assert status_of(ps, "P-NOISE") == "made"
    assert status_of(ps, "P-EMPTY") == "made"
    assert flags_of(ps, "P-TALK") == ["announced only"]


def test_rollup_single_negative_article_never_breaks_a_promise(promise_store):
    """The old rule let one `broken` vote override everything."""
    ps = promise_store
    ps.add_promise("P", "t", "gazdasag")
    add_evidence(ps, "P", "S1", "step", "Index", "2026-06-01")
    add_evidence(ps, "P", "R1", "reversal", "Magyar Nemzet", "2026-10-06")

    rollup(ps)

    assert status_of(ps, "P") == "in_progress"
    assert flags_of(ps, "P") == ["disputed: 1 uncorroborated reversal report(s)"]


def test_rollup_corroborated_reversal_goes_to_review(promise_store):
    ps = promise_store
    ps.add_promise("P", "t", "gazdasag")
    add_evidence(ps, "P", "R1", "reversal", "Telex", "2026-09-01")
    add_evidence(ps, "P", "R2", "reversal", "HVG", "2026-09-02")

    rollup(ps)
    assert status_of(ps, "P") == "made"
    assert flags_of(ps, "P") == ["review: reversal reported by 2 outlets"]

    cfg = {**LLM_CFG, "rollup": {"enabled": True, "auto_publish_broken": True}}
    rollup(ps, cfg)
    assert status_of(ps, "P") == "broken"


def test_rollup_is_cumulative_and_stable(promise_store):
    """Old evidence does not age out, and re-running changes nothing."""
    ps = promise_store
    ps.add_promise("P", "t", "gazdasag")
    add_evidence(ps, "P", "K1", "kept", "Telex", "2026-05-20")
    add_evidence(ps, "P", "K2", "kept", "HVG", "2026-05-21")
    rollup(ps)
    assert status_of(ps, "P") == "kept"

    for i in range(8):  # later coverage that merely discusses the promise
        add_evidence(ps, "P", f"LATER{i}", "intent", "Index", f"2026-09-{i + 1:02d}")
    rollup(ps)
    rollup(ps)

    assert status_of(ps, "P") == "kept"
    assert len(ps.get_status_history("P")) == 1


def test_rollup_ignores_verdicts_of_another_prompt_version(promise_store):
    ps = promise_store
    ps.add_promise("P", "t", "gazdasag")
    add_evidence(ps, "P", "OLD1", "kept", "Telex", version="v0")
    add_evidence(ps, "P", "OLD2", "kept", "HVG", version="v0")
    # Pretend the stale rows need no new work, so only the version filter acts.
    with sqlite3.connect(ps.db_path) as conn:
        conn.execute("UPDATE llm_classifications SET pass1_relevant = 0")
        conn.commit()

    rollup(ps)
    assert status_of(ps, "P") == "made"


def test_rollup_returns_promise_to_made_when_evidence_is_gone(promise_store):
    """A status that rested on a dismissed article does not linger."""
    ps = promise_store
    ps.add_promise("P", "t", "gazdasag")
    ps.update_status("P", "broken", evidence="llm-rollup: broken=1", source="rollup")
    add_evidence(ps, "P", "E1", "none")

    rollup(ps)

    assert status_of(ps, "P") == "made"
    assert ps.get_status_history("P")[-1]["evidence"] == "llm-rollup"


def test_rollup_waits_for_links_still_to_be_classified(promise_store):
    """Half the evidence must not produce a status that flickers back later."""
    ps = promise_store
    ps.add_promise("P", "t", "gazdasag")
    ps.update_status("P", "kept", source="rollup")
    add_evidence(ps, "P", "K1", "kept", "Telex")
    ps.link_article("P", "NOT-YET", relevance_score=0.4)

    rollup(ps)
    assert status_of(ps, "P") == "kept"

    add_evidence(ps, "P", "NOT-YET", "kept", "HVG")
    rollup(ps)
    assert status_of(ps, "P") == "kept"
    assert len(ps.get_status_history("P")) == 1


def test_rollup_waits_while_a_failed_link_can_still_be_retried(promise_store):
    ps = promise_store
    ps.add_promise("P", "t", "gazdasag")
    add_evidence(ps, "P", "S1", "step")
    ps.link_article("P", "FAIL", relevance_score=0.4)
    ps.upsert_classification("P", "FAIL", error="pass2: timeout", prompt_version=VERSION)

    rollup(ps)
    assert status_of(ps, "P") == "made"

    for _ in range(2):  # third failure: given up
        ps.upsert_classification("P", "FAIL", error="pass2: timeout", prompt_version=VERSION)
    rollup(ps)
    assert status_of(ps, "P") == "in_progress"


def test_rollup_records_basis_articles_in_history(promise_store):
    ps = promise_store
    ps.add_promise("P", "t", "gazdasag")
    add_evidence(ps, "P", "K2", "kept", "HVG", "2026-07-02")
    add_evidence(ps, "P", "K1", "kept", "Telex", "2026-07-01")
    add_evidence(ps, "P", "S1", "step", "Index", "2026-06-01")

    rollup(ps)

    history = ps.get_status_history("P")
    assert len(history) == 1
    assert history[0]["evidence"] == "llm-rollup: kept=2, step=1"
    assert history[0]["article_ids"] == "K1,K2"
    assert history[0]["source"] == "rollup"


def test_rollup_skip_flag_bypasses(promise_store):
    ps = promise_store
    ps.add_promise("P", "t", "gazdasag")
    add_evidence(ps, "P", "S1", "step")

    _maybe_rollup(ps, LLM_CFG, skip=True)
    assert status_of(ps, "P") == "made"


def test_rollup_disabled_in_config_bypasses(promise_store):
    ps = promise_store
    ps.add_promise("P", "t", "gazdasag")
    add_evidence(ps, "P", "S1", "step")

    _maybe_rollup(ps, {"rollup": {"enabled": False}}, skip=False)
    assert status_of(ps, "P") == "made"


# ---------------------------------------------------------------------------
# Rollup: manual statuses, deadlines, kinds
# ---------------------------------------------------------------------------


def test_rollup_does_not_overwrite_a_manual_status(promise_store):
    """A status set by hand used to be undone by the next pipeline run."""
    ps = promise_store
    ps.add_promise("P", "t", "gazdasag")
    add_evidence(ps, "P", "S1", "step")
    ps.update_status("P", "kept", evidence="Manual override: read the decree")

    rollup(ps)

    assert status_of(ps, "P") == "kept"
    assert flags_of(ps, "P") == [
        "review: manual status 'kept' differs from evidence-based 'in_progress'"
    ]
    assert len(ps.get_status_history("P")) == 1


def test_rollup_resumes_after_unlock(promise_store):
    ps = promise_store
    ps.add_promise("P", "t", "gazdasag")
    add_evidence(ps, "P", "S1", "step")
    ps.update_status("P", "kept")
    ps.set_status_lock("P", False)

    rollup(ps)
    assert status_of(ps, "P") == "in_progress"
    assert flags_of(ps, "P") == []


def test_rollup_locked_status_that_matches_evidence_has_no_flag(promise_store):
    ps = promise_store
    ps.add_promise("P", "t", "gazdasag")
    add_evidence(ps, "P", "S1", "step")
    ps.update_status("P", "in_progress")

    rollup(ps)
    assert flags_of(ps, "P") == []


@pytest.mark.parametrize("manual_status", ["abandoned", "modified"])
def test_rollup_leaves_statuses_only_a_person_assigns(promise_store, manual_status):
    ps = promise_store
    ps.add_promise("P", "t", "gazdasag")
    ps.update_status("P", manual_status, lock=False)
    add_evidence(ps, "P", "S1", "step")

    rollup(ps)
    assert status_of(ps, "P") == manual_status


def test_rollup_lapsed_deadline_is_flagged_not_broken(promise_store):
    ps = promise_store
    ps.add_promise("P", "t", "gazdasag", deadline="2026-06-01")

    rollup(ps)

    assert status_of(ps, "P") == "made"
    assert flags_of(ps, "P") == ["review: deadline lapsed with no delivery on record"]


def test_rollup_clears_flags_that_no_longer_apply(promise_store):
    ps = promise_store
    ps.add_promise("P", "t", "gazdasag", deadline="2026-06-01")
    rollup(ps)
    assert flags_of(ps, "P")

    add_evidence(ps, "P", "K1", "kept", "Telex")
    add_evidence(ps, "P", "K2", "kept", "HVG")
    rollup(ps)
    assert status_of(ps, "P") == "kept"
    assert flags_of(ps, "P") == []


def test_rollup_uses_the_promise_kind(promise_store):
    ps = promise_store
    ps.add_promise("ONGOING", "Megtartjuk.", "gazdasag", kind="ongoing")
    ps.add_promise("ONE-OFF", "Létrehozzuk.", "gazdasag", kind="one_off")
    for pid in ("ONGOING", "ONE-OFF"):
        add_evidence(ps, pid, f"{pid}-1", "kept", "Telex")
        add_evidence(ps, pid, f"{pid}-2", "kept", "HVG")

    rollup(ps)

    assert status_of(ps, "ONGOING") == "in_progress"
    assert status_of(ps, "ONE-OFF") == "kept"


def test_rollup_infers_target_kind_from_a_year_deadline(promise_store):
    ps = promise_store
    ps.add_promise("P", "2030-ra elérjük.", "gazdasag", deadline="2030")
    add_evidence(ps, "P", "R1", "reversal", "Telex")
    add_evidence(ps, "P", "R2", "reversal", "HVG")

    cfg = {**LLM_CFG, "rollup": {"enabled": True, "auto_publish_broken": True}}
    rollup(ps, cfg)
    assert status_of(ps, "P") == "made"
    assert flags_of(ps, "P") == ["review: reversal reported by 2 outlets"]


def test_rollup_min_outlets_is_configurable(promise_store):
    ps = promise_store
    ps.add_promise("P", "t", "gazdasag")
    add_evidence(ps, "P", "K1", "kept", "Telex")

    rollup(ps, {**LLM_CFG, "rollup": {"enabled": True, "min_outlets": 1}})
    assert status_of(ps, "P") == "kept"


# ---------------------------------------------------------------------------
# _format_evidence
# ---------------------------------------------------------------------------


def test_format_evidence_single_signal():
    assert _format_evidence(Counter({"kept": 2})) == "llm-rollup: kept=2"


def test_format_evidence_sorted_keys():
    """Output ordering must be deterministic for stable commit diffs."""
    out = _format_evidence(Counter({"kept": 2, "reversal": 1, "step": 3}))
    assert out == "llm-rollup: kept=2, reversal=1, step=3"


def test_format_evidence_empty_counter():
    assert _format_evidence(Counter()) == "llm-rollup"


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
# _resolve_article — text from article_text.db, metadata from the feed DBs
# ---------------------------------------------------------------------------


class _FakeDB:
    """Minimal stand-in for DatabaseManager exposing the methods used by
    ``_resolve_article``: ``get_article_text`` + ``get_connection``."""

    def __init__(self, article_text=None, current_rows=None, history_rows=None,
                 all_feeds_rows=None):
        self._article_text = article_text or {}
        self._sources = {
            "current": current_rows or {},
            "history": history_rows or {},
            "all_feeds": all_feeds_rows or {},
        }
        self.queries = []

    def get_article_text(self, entry_id):
        self.queries.append(("article_text", entry_id))
        return self._article_text.get(entry_id)

    def get_connection(self, db_key, row_factory=True):
        self.queries.append((db_key, None))
        source = self._sources[db_key]

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
    db = _FakeDB(
        article_text={
            "E1": {"title": "AT title", "summary": "AT summary",
                   "full_text": "AT body", "url": "https://at"},
        },
        current_rows={"E1": {"title": "other", "summary": "other"}},
    )
    article = _resolve_article(db, "E1")
    assert article["title"] == "AT title"
    assert article["summary"] == "AT summary"
    assert article["full_text"] == "AT body"
    assert article["url"] == "https://at"


def test_resolve_article_falls_back_to_papers():
    db = _FakeDB(current_rows={
        "E1": {"title": "From papers", "summary": "p summary", "link": "https://p",
               "feed_name": "Telex", "published_date": "2026-06-10"},
    })
    article = _resolve_article(db, "E1")
    assert article["title"] == "From papers"
    assert article["summary"] == "p summary"
    assert article["full_text"] is None
    assert article["url"] == "https://p"
    assert article["outlet"] == "Telex"
    assert article["published"] == "2026-06-10"


def test_resolve_article_falls_back_to_history():
    db = _FakeDB(history_rows={
        "E1": {"title": "From history", "summary": "h summary"},
    })
    article = _resolve_article(db, "E1")
    assert article["title"] == "From history"
    assert article["summary"] == "h summary"
    assert article["full_text"] is None
    assert article["outlet"] is None


def test_resolve_article_falls_back_to_all_feeds():
    db = _FakeDB(all_feeds_rows={
        "E1": {"title": "From feeds", "summary": "f", "link": "https://f",
               "feed_name": "HVG", "published_date": "2026-07-01"},
    })
    article = _resolve_article(db, "E1")
    assert article["title"] == "From feeds"
    assert article["outlet"] == "HVG"


def test_resolve_article_takes_outlet_and_date_from_feed_dbs():
    """article_text.db has the text but not where or when it appeared."""
    db = _FakeDB(
        article_text={"E1": {"title": "T", "summary": "S", "full_text": "B", "url": ""}},
        all_feeds_rows={"E1": {"title": "feed title", "summary": "feed summary",
                               "link": "https://feed", "feed_name": "Index",
                               "published_date": "2026-08-15 10:00:00"}},
    )
    article = _resolve_article(db, "E1")
    assert article["title"] == "T"  # text still comes from article_text.db
    assert article["full_text"] == "B"
    assert article["url"] == "https://feed"
    assert article["outlet"] == "Index"
    assert article["published"] == "2026-08-15"


def test_resolve_article_returns_none_when_nowhere_found():
    assert _resolve_article(_FakeDB(), "NOPE") is None


def test_resolve_article_skips_empty_article_text_row():
    """A row with only NULL/empty fields shouldn't short-circuit the cascade."""
    db = _FakeDB(
        article_text={"E1": {"title": None, "summary": None, "full_text": None}},
        current_rows={"E1": {"title": "real title", "summary": "s"}},
    )
    article = _resolve_article(db, "E1")
    assert article["title"] == "real title"
    assert article["full_text"] is None


def test_resolve_article_handles_article_text_with_only_title():
    """A paywalled/failed fetch may have title but no body; that still wins."""
    db = _FakeDB(article_text={
        "E1": {"title": "just the headline", "summary": None, "full_text": None},
    })
    article = _resolve_article(db, "E1")
    assert article["title"] == "just the headline"
    assert article["summary"] == ""
    assert article["full_text"] is None


def test_resolve_article_strips_markup_and_paywall_notice():
    db = _FakeDB(article_text={
        "E1": {"title": "T", "summary": "<p>Teaser&nbsp;text</p>",
               "full_text": "A cikk szövege. Kedves Olvasónk! Fizessen elő."},
    })
    article = _resolve_article(db, "E1")
    assert article["summary"] == "Teaser\xa0text"
    assert article["full_text"] == "A cikk szövege."


# ---------------------------------------------------------------------------
# run — end to end against real databases, with a scripted model and fetcher
# ---------------------------------------------------------------------------

BODY = (
    "Az Országgyűlés kedden elfogadta a törvényt, amely teljesíti az ígéretet. "
    + "A részletekről a miniszter számolt be. " * 12
).strip()
GATE_OK = {"relevant": True, "confidence": 0.9, "reason": ""}
GATE_NO = {"relevant": False, "confidence": 0.8, "reason": "off-topic"}
DELIVERED = {
    "what_happened": "Parliament adopted the law on 2026-06-09.",
    "about_promise": True, "actor": "current_government",
    "evidence_type": "delivered", "scope": "full", "event_date": "2026-06-09",
    "quote": "Az Országgyűlés kedden elfogadta a törvényt", "confidence": 0.85,
}


class _ScriptedOpenAI:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    @property
    def chat(self):
        return SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **request):
        self.calls.append(request)
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(item)))]
        )


class _ScriptedFetcher:
    fetched: list = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def fetch_text(self, url):
        type(self).fetched.append(url)
        return BODY, "ok"


@pytest.fixture
def pipeline(tmp_data_dir: Path, monkeypatch):
    """Config, databases and one promise with two linked feed entries."""
    from tisza_tracker.core.config import ConfigManager
    from tisza_tracker.core.database import DatabaseManager
    from tisza_tracker.core.promise_store import PromiseStore

    config_path = str(tmp_data_dir / "config" / "config.yaml")
    config = ConfigManager(config_path).load_config()
    db = DatabaseManager(config)
    ps = PromiseStore(config)
    ps.add_promise("P-1", "Elfogadjuk a törvényt.", "gazdasag")

    with sqlite3.connect(db.db_paths["all_feeds"]) as conn:
        for eid, feed in (("E-TELEX", "Telex"), ("E-HVG", "HVG")):
            conn.execute(
                "INSERT INTO feed_entries (entry_id, feed_name, title, link, summary, "
                "published_date) VALUES (?, ?, ?, ?, ?, ?)",
                (eid, feed, "Elfogadták a törvényt", f"https://{feed}.example/cikk",
                 "Kedden szavaztak.", "2026-06-10"),
            )
        conn.commit()
    ps.link_article("P-1", "E-TELEX", relevance_score=0.9)
    ps.link_article("P-1", "E-HVG", relevance_score=0.8)

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(classify_cmd, "ArticleFetcher", _ScriptedFetcher)
    monkeypatch.setattr(
        "tisza_tracker.processors.llm_classifier.time.sleep", lambda *_: None,
    )
    _ScriptedFetcher.fetched = []

    def run(responses, **kwargs):
        fake = _ScriptedOpenAI(responses)
        with patch("openai.OpenAI", lambda **_: fake):
            result = classify_cmd.run(config_path, **kwargs)
        return result, fake

    return SimpleNamespace(run=run, ps=ps, db=db, config=config)


def test_run_fetches_body_extracts_and_rolls_up(pipeline):
    result, fake = pipeline.run([GATE_OK, DELIVERED, GATE_OK, DELIVERED])

    assert result == {"classified": 2, "errors": 0, "irrelevant": 0, "total_candidates": 2}
    assert _ScriptedFetcher.fetched == ["https://Telex.example/cikk", "https://HVG.example/cikk"]

    row = pipeline.ps.get_classification("P-1", "E-TELEX")
    assert row["signal"] == "kept"
    assert row["outlet"] == "Telex"
    assert row["published_date"] == "2026-06-10"
    assert row["body_chars"] == len(BODY)
    assert row["quote_verbatim"] == 1
    assert row["prompt_version"] == effective_prompt_version(
        pipeline.config["llm_classification"]
    )
    # The body is cached for later runs and for full-text search.
    assert pipeline.db.get_article_text("E-TELEX")["full_text"] == BODY

    promise = pipeline.ps.get_promise("P-1")
    assert promise["current_status"] == "kept"
    history = pipeline.ps.get_status_history("P-1")
    assert history[-1]["article_ids"] == "E-HVG,E-TELEX"
    assert pipeline.ps.get_best_article("P-1") is not None


def test_run_does_not_download_articles_the_gate_rejects(pipeline):
    result, _ = pipeline.run([GATE_NO, GATE_NO])

    assert result["irrelevant"] == 2
    assert _ScriptedFetcher.fetched == []
    assert pipeline.ps.get_classification("P-1", "E-TELEX")["signal"] == "none"
    assert pipeline.ps.get_promise("P-1")["current_status"] == "made"


def test_run_is_idempotent(pipeline):
    pipeline.run([GATE_OK, DELIVERED, GATE_OK, DELIVERED])
    result, fake = pipeline.run([])
    assert result == {"classified": 0, "total_candidates": 0}
    assert fake.calls == []


def test_run_retries_a_failed_link_on_the_next_run(pipeline):
    boom = RuntimeError("upstream timeout")
    result, _ = pipeline.run([GATE_OK, DELIVERED, GATE_OK, boom, boom, boom])
    assert result["errors"] == 1
    # One link failed, so the promise waits rather than settle on half the evidence.
    assert pipeline.ps.get_promise("P-1")["current_status"] == "made"

    result, fake = pipeline.run([GATE_OK, DELIVERED])
    assert result["classified"] == 1
    assert len(fake.calls) == 2
    assert pipeline.ps.get_classification("P-1", "E-HVG")["error"] is None
    assert pipeline.ps.get_promise("P-1")["current_status"] == "kept"


def test_run_records_unresolvable_article_so_it_stops_blocking(pipeline):
    pipeline.ps.link_article("P-1", "E-GHOST", relevance_score=0.99)

    for _ in range(3):
        pipeline.run([GATE_OK, DELIVERED, GATE_OK, DELIVERED], force=True)

    ghost = pipeline.ps.get_classification("P-1", "E-GHOST")
    assert ghost["error"] == "article not found in any database"
    assert ghost["attempts"] == 3
    assert pipeline.ps.get_promise("P-1")["current_status"] == "kept"


def test_run_force_redoes_gate_rejections(pipeline):
    pipeline.run([GATE_NO, GATE_NO])
    result, _ = pipeline.run([GATE_OK, DELIVERED, GATE_OK, DELIVERED], force=True)
    assert result["classified"] == 2
    assert pipeline.ps.get_promise("P-1")["current_status"] == "kept"


def test_run_skipped_when_disabled(tmp_data_dir, monkeypatch):
    monkeypatch.setattr(classify_cmd, "_load_llm_config", lambda config: {"enabled": False})
    result = classify_cmd.run(str(tmp_data_dir / "config" / "config.yaml"))
    assert result == {"classified": 0, "skipped_disabled": True}
