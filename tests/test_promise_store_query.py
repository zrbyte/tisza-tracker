"""Tests for ``PromiseStore.get_promises_with_articles``.

Exercises the cross-database JOIN (ATTACH papers + history), LLM-verdict
merging, irrelevant-dropping, top-N capping, and the confidence-first sort.
"""

from __future__ import annotations

from pathlib import Path


def test_articles_enriched_with_verdict_and_quote(
    seeded_promises, papers_db, history_db, insert_paper_entry,
):
    ps = seeded_promises
    insert_paper_entry(papers_db, "E1", "Article 1", "https://a")
    ps.link_article("PROM-001", "E1", relevance_score=0.5)
    ps.upsert_classification(
        "PROM-001", "E1",
        verdict="kept", confidence=0.8,
        evidence_quote="idézet", reasoning="ok",
        model="m", prompt_version="v1",
    )

    promises = ps.get_promises_with_articles(
        str(papers_db), history_db_path=str(history_db),
    )
    target = next(p for p in promises if p["id"] == "PROM-001")
    assert len(target["articles"]) == 1
    a = target["articles"][0]
    assert a["title"] == "Article 1"
    assert a["verdict"] == "kept"
    assert a["confidence"] == 0.8
    assert a["evidence_quote"] == "idézet"


def test_drop_irrelevant_default(
    seeded_promises, papers_db, history_db, insert_paper_entry,
):
    ps = seeded_promises
    insert_paper_entry(papers_db, "KEEP", "Keep", "https://keep")
    insert_paper_entry(papers_db, "DROP", "Drop", "https://drop")
    ps.link_article("PROM-001", "KEEP", relevance_score=0.5)
    ps.link_article("PROM-001", "DROP", relevance_score=0.6)
    ps.upsert_classification("PROM-001", "KEEP", verdict="kept", confidence=0.9, prompt_version="v1")
    ps.upsert_classification("PROM-001", "DROP", verdict="irrelevant", confidence=0.9, prompt_version="v1")

    promises = ps.get_promises_with_articles(
        str(papers_db), history_db_path=str(history_db),
    )
    target = next(p for p in promises if p["id"] == "PROM-001")
    ids = [a["entry_id"] for a in target["articles"]]
    assert ids == ["KEEP"]


def test_drop_irrelevant_can_be_disabled(
    seeded_promises, papers_db, history_db, insert_paper_entry,
):
    ps = seeded_promises
    insert_paper_entry(papers_db, "E1", "A1", "https://a1")
    ps.link_article("PROM-001", "E1", relevance_score=0.5)
    ps.upsert_classification("PROM-001", "E1", verdict="irrelevant", confidence=0.9, prompt_version="v1")

    promises = ps.get_promises_with_articles(
        str(papers_db), history_db_path=str(history_db),
        drop_irrelevant=False,
    )
    target = next(p for p in promises if p["id"] == "PROM-001")
    assert len(target["articles"]) == 1


def test_max_per_promise_caps_output(
    seeded_promises, papers_db, history_db, insert_paper_entry,
):
    ps = seeded_promises
    for i in range(5):
        insert_paper_entry(papers_db, f"E{i}", f"Title {i}", f"https://{i}")
        ps.link_article("PROM-001", f"E{i}", relevance_score=0.5 - i * 0.01)
        ps.upsert_classification(
            "PROM-001", f"E{i}",
            verdict="in_progress", confidence=0.5 - i * 0.05,
            prompt_version="v1",
        )

    promises = ps.get_promises_with_articles(
        str(papers_db), history_db_path=str(history_db),
        max_per_promise=3,
    )
    target = next(p for p in promises if p["id"] == "PROM-001")
    assert len(target["articles"]) == 3


def test_sort_by_confidence_then_score(
    seeded_promises, papers_db, history_db, insert_paper_entry,
):
    """Higher confidence wins over higher similarity score."""
    ps = seeded_promises
    # A = lower confidence but higher score; B = higher confidence, lower score
    insert_paper_entry(papers_db, "A", "A", "https://a")
    insert_paper_entry(papers_db, "B", "B", "https://b")
    ps.link_article("PROM-001", "A", relevance_score=0.9)
    ps.link_article("PROM-001", "B", relevance_score=0.3)
    ps.upsert_classification("PROM-001", "A", verdict="in_progress", confidence=0.3, prompt_version="v1")
    ps.upsert_classification("PROM-001", "B", verdict="in_progress", confidence=0.9, prompt_version="v1")

    promises = ps.get_promises_with_articles(
        str(papers_db), history_db_path=str(history_db),
    )
    target = next(p for p in promises if p["id"] == "PROM-001")
    ids = [a["entry_id"] for a in target["articles"]]
    assert ids == ["B", "A"]


def test_unclassified_articles_sort_after_classified(
    seeded_promises, papers_db, history_db, insert_paper_entry,
):
    """Entries without a verdict (confidence=None) rank below classified ones."""
    ps = seeded_promises
    insert_paper_entry(papers_db, "C", "Classified", "https://c")
    insert_paper_entry(papers_db, "U", "Unclassified", "https://u")
    ps.link_article("PROM-001", "C", relevance_score=0.3)
    ps.link_article("PROM-001", "U", relevance_score=0.9)
    ps.upsert_classification("PROM-001", "C", verdict="kept", confidence=0.5, prompt_version="v1")
    # No classification for "U"

    promises = ps.get_promises_with_articles(
        str(papers_db), history_db_path=str(history_db),
    )
    target = next(p for p in promises if p["id"] == "PROM-001")
    ids = [a["entry_id"] for a in target["articles"]]
    assert ids == ["C", "U"]


def test_history_fallback_when_not_in_papers(
    seeded_promises, papers_db, history_db, insert_history_entry,
):
    ps = seeded_promises
    insert_history_entry(history_db, "H1", "History Only", "https://h1")
    ps.link_article("PROM-001", "H1", relevance_score=0.5)
    ps.upsert_classification(
        "PROM-001", "H1", verdict="broken", confidence=0.8, prompt_version="v1",
    )

    promises = ps.get_promises_with_articles(
        str(papers_db), history_db_path=str(history_db),
    )
    target = next(p for p in promises if p["id"] == "PROM-001")
    assert len(target["articles"]) == 1
    assert target["articles"][0]["title"] == "History Only"
    assert target["articles"][0]["verdict"] == "broken"


def test_papers_takes_precedence_over_history(
    seeded_promises, papers_db, history_db,
    insert_paper_entry, insert_history_entry,
):
    """An entry_id in both DBs should use the papers.db title."""
    ps = seeded_promises
    insert_paper_entry(papers_db, "E1", "Papers Title", "https://p")
    insert_history_entry(history_db, "E1", "History Title", "https://h")
    ps.link_article("PROM-001", "E1", relevance_score=0.5)

    promises = ps.get_promises_with_articles(
        str(papers_db), history_db_path=str(history_db),
    )
    target = next(p for p in promises if p["id"] == "PROM-001")
    assert len(target["articles"]) == 1
    assert target["articles"][0]["title"] == "Papers Title"


def test_empty_articles_when_no_links(seeded_promises, papers_db, history_db):
    promises = seeded_promises.get_promises_with_articles(
        str(papers_db), history_db_path=str(history_db),
    )
    for p in promises:
        assert p["articles"] == []


def test_category_filter(seeded_promises, papers_db, history_db):
    promises = seeded_promises.get_promises_with_articles(
        str(papers_db), history_db_path=str(history_db),
        category="oktatas",
    )
    assert {p["id"] for p in promises} == {"PROM-003"}


def test_article_matched_to_multiple_topics_not_duplicated(
    seeded_promises, papers_db, history_db, insert_paper_entry,
):
    """Regression: papers.entries PK is (id, topic), so the same article
    appears once per matched topic.  The JOIN must not leak duplicates into
    the promise's articles list."""
    # Same entry_id, same title/link, but two different topics
    insert_paper_entry(papers_db, "DUPE", "Shared Article", "https://dup", topic="gazdasag")
    insert_paper_entry(papers_db, "DUPE", "Shared Article", "https://dup", topic="korrupcio")
    seeded_promises.link_article("PROM-001", "DUPE", relevance_score=0.5)

    promises = seeded_promises.get_promises_with_articles(
        str(papers_db), history_db_path=str(history_db),
    )
    target = next(p for p in promises if p["id"] == "PROM-001")
    assert len(target["articles"]) == 1
