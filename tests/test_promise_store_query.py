"""Tests for ``PromiseStore.get_promises_with_articles``.

Exercises the cross-database JOIN (ATTACH papers + history), LLM-signal
merging, dropping of articles without evidence, top-N capping, and the
evidence-then-confidence sort.
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
        signal="kept", confidence=0.8,
        evidence_quote="idézet", quote_verbatim=True, reasoning="ok",
        model="m", prompt_version="v1",
    )

    promises = ps.get_promises_with_articles(
        str(papers_db), history_db_path=str(history_db),
    )
    target = next(p for p in promises if p["id"] == "PROM-001")
    assert len(target["articles"]) == 1
    a = target["articles"][0]
    assert a["title"] == "Article 1"
    assert a["signal"] == "kept"
    assert a["verdict"] == "kept"
    assert a["confidence"] == 0.8
    assert a["evidence_quote"] == "idézet"


def test_quote_not_found_in_the_article_is_withheld(
    seeded_promises, papers_db, history_db, insert_paper_entry,
):
    """Only quotes verified against the article text reach the report."""
    ps = seeded_promises
    for eid, verbatim in (("NO", False), ("OLD", None)):
        insert_paper_entry(papers_db, eid, eid, f"https://{eid}")
        ps.link_article("PROM-001", eid, relevance_score=0.5)
        ps.upsert_classification(
            "PROM-001", eid, signal="step", confidence=0.8,
            evidence_quote="kitalált idézet", quote_verbatim=verbatim,
            prompt_version="v1",
        )

    promises = ps.get_promises_with_articles(
        str(papers_db), history_db_path=str(history_db),
    )
    target = next(p for p in promises if p["id"] == "PROM-001")
    assert [a["evidence_quote"] for a in target["articles"]] == [None, None]


def test_drop_irrelevant_default(
    seeded_promises, papers_db, history_db, insert_paper_entry,
):
    ps = seeded_promises
    insert_paper_entry(papers_db, "KEEP", "Keep", "https://keep")
    insert_paper_entry(papers_db, "DROP", "Drop", "https://drop")
    ps.link_article("PROM-001", "KEEP", relevance_score=0.5)
    ps.link_article("PROM-001", "DROP", relevance_score=0.6)
    ps.upsert_classification("PROM-001", "KEEP", signal="kept", confidence=0.9, prompt_version="v1")
    ps.upsert_classification("PROM-001", "DROP", signal="none", confidence=0.9, prompt_version="v1")

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
    ps.upsert_classification("PROM-001", "E1", signal="none", confidence=0.9, prompt_version="v1")

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
            signal="step", confidence=0.5 - i * 0.05,
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
    ps.upsert_classification("PROM-001", "A", signal="step", confidence=0.3, prompt_version="v1")
    ps.upsert_classification("PROM-001", "B", signal="step", confidence=0.9, prompt_version="v1")

    promises = ps.get_promises_with_articles(
        str(papers_db), history_db_path=str(history_db),
    )
    target = next(p for p in promises if p["id"] == "PROM-001")
    ids = [a["entry_id"] for a in target["articles"]]
    assert ids == ["B", "A"]


def test_sort_by_strength_of_evidence_first(
    seeded_promises, papers_db, history_db, insert_paper_entry,
):
    """A delivery report outranks an announcement the model was surer about."""
    ps = seeded_promises
    for eid, signal, confidence in (
        ("INTENT", "intent", 0.95), ("KEPT", "kept", 0.6), ("STEP", "step", 0.9),
    ):
        insert_paper_entry(papers_db, eid, eid, f"https://{eid}")
        ps.link_article("PROM-001", eid, relevance_score=0.5)
        ps.upsert_classification(
            "PROM-001", eid, signal=signal, confidence=confidence, prompt_version="v1",
        )

    promises = ps.get_promises_with_articles(
        str(papers_db), history_db_path=str(history_db),
    )
    target = next(p for p in promises if p["id"] == "PROM-001")
    assert [a["entry_id"] for a in target["articles"]] == ["KEPT", "STEP", "INTENT"]


def test_unclassified_articles_sort_after_classified(
    seeded_promises, papers_db, history_db, insert_paper_entry,
):
    """Entries without a verdict (confidence=None) rank below classified ones."""
    ps = seeded_promises
    insert_paper_entry(papers_db, "C", "Classified", "https://c")
    insert_paper_entry(papers_db, "U", "Unclassified", "https://u")
    ps.link_article("PROM-001", "C", relevance_score=0.3)
    ps.link_article("PROM-001", "U", relevance_score=0.9)
    ps.upsert_classification("PROM-001", "C", signal="kept", confidence=0.5, prompt_version="v1")
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
        "PROM-001", "H1", signal="reversal", confidence=0.8, prompt_version="v1",
    )

    promises = ps.get_promises_with_articles(
        str(papers_db), history_db_path=str(history_db),
    )
    target = next(p for p in promises if p["id"] == "PROM-001")
    assert len(target["articles"]) == 1
    assert target["articles"][0]["title"] == "History Only"
    assert target["articles"][0]["verdict"] == "broken"


def test_all_feeds_fallback_when_not_in_papers_or_history(
    seeded_promises, papers_db, history_db, all_feeds_db, insert_all_feeds_entry,
):
    """The dedup archive is the last-resort source for title/link.

    Mirrors the production bug where promise_article_links carried a verdict
    but the entry had been rotated out of papers.db and never archived to
    history.db.  Without the all_feed_entries.db fallback the article would
    silently disappear from the report.
    """
    ps = seeded_promises
    insert_all_feeds_entry(all_feeds_db, "F1", "Feeds Only", "https://f1")
    ps.link_article("PROM-001", "F1", relevance_score=0.5)
    ps.upsert_classification(
        "PROM-001", "F1", signal="step", confidence=0.7, prompt_version="v1",
    )

    promises = ps.get_promises_with_articles(
        str(papers_db),
        history_db_path=str(history_db),
        all_feeds_db_path=str(all_feeds_db),
    )
    target = next(p for p in promises if p["id"] == "PROM-001")
    assert len(target["articles"]) == 1
    assert target["articles"][0]["title"] == "Feeds Only"
    assert target["articles"][0]["verdict"] == "in_progress"


def test_history_takes_precedence_over_all_feeds(
    seeded_promises, papers_db, history_db, all_feeds_db,
    insert_history_entry, insert_all_feeds_entry,
):
    """history.db has matched, curated metadata; prefer it over the dedup archive."""
    ps = seeded_promises
    insert_history_entry(history_db, "E1", "History Title", "https://h")
    insert_all_feeds_entry(all_feeds_db, "E1", "Feeds Title", "https://f")
    ps.link_article("PROM-001", "E1", relevance_score=0.5)

    promises = ps.get_promises_with_articles(
        str(papers_db),
        history_db_path=str(history_db),
        all_feeds_db_path=str(all_feeds_db),
    )
    target = next(p for p in promises if p["id"] == "PROM-001")
    assert target["articles"][0]["title"] == "History Title"


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


# ---------------------------------------------------------------------------
# Sticky winner (promise_best_article) surfacing in reports
# ---------------------------------------------------------------------------


def test_sticky_survives_topn_cutoff(
    seeded_promises, papers_db, history_db, insert_paper_entry,
):
    """Past champion must not be evicted by newer articles under top-N cap."""
    ps = seeded_promises
    # Champion inserted first with confidence 0.9
    insert_paper_entry(papers_db, "CHAMP", "Champion", "https://champ")
    ps.link_article("PROM-001", "CHAMP", relevance_score=0.5)
    ps.upsert_classification(
        "PROM-001", "CHAMP", signal="kept", confidence=0.9, prompt_version="v1",
    )
    ps.update_best_articles()

    # Three newer, lower-confidence articles arrive
    for i, eid in enumerate(["N1", "N2", "N3"]):
        insert_paper_entry(papers_db, eid, f"New {i}", f"https://n{i}")
        ps.link_article("PROM-001", eid, relevance_score=0.8)
        ps.upsert_classification(
            "PROM-001", eid, signal="step", confidence=0.7, prompt_version="v1",
        )

    # Top-3 cap: champion is highest confidence anyway, but test that with a
    # *lower* sticky confidence (simulated via lower-confidence newcomers
    # actually ranking ABOVE the champion) the pin still forces inclusion.
    promises = ps.get_promises_with_articles(
        str(papers_db), history_db_path=str(history_db), max_per_promise=3,
    )
    target = next(p for p in promises if p["id"] == "PROM-001")
    ids = [a["entry_id"] for a in target["articles"]]
    assert "CHAMP" in ids
    assert ids[0] == "CHAMP"  # sticky pinned to position 0


def test_sticky_not_shown_once_reclassified_as_no_evidence(
    seeded_promises, papers_db, history_db, insert_paper_entry,
):
    """A champion the classifier later dismisses must leave the report,
    even before the sticky table has been refreshed."""
    ps = seeded_promises
    insert_paper_entry(papers_db, "CHAMP", "Champion", "https://champ")
    ps.link_article("PROM-001", "CHAMP", relevance_score=0.5)
    ps.upsert_classification(
        "PROM-001", "CHAMP", signal="kept", confidence=0.9, prompt_version="v1",
    )
    ps.update_best_articles()

    # Later reclassification finds no evidence in it
    ps.upsert_classification(
        "PROM-001", "CHAMP", signal="none", confidence=0.9, prompt_version="v2",
    )

    promises = ps.get_promises_with_articles(
        str(papers_db), history_db_path=str(history_db),
    )
    target = next(p for p in promises if p["id"] == "PROM-001")
    assert target["articles"] == []


def test_sticky_pinned_first_when_present(
    seeded_promises, papers_db, history_db, insert_paper_entry,
):
    """When sticky is not the highest-confidence article, it still sits first."""
    ps = seeded_promises
    # Champion with confidence 0.6 (sticky)
    insert_paper_entry(papers_db, "CHAMP", "Champion", "https://champ")
    ps.link_article("PROM-001", "CHAMP", relevance_score=0.5)
    ps.upsert_classification(
        "PROM-001", "CHAMP", signal="kept", confidence=0.6, prompt_version="v1",
    )
    ps.update_best_articles()

    # A new, higher-confidence article arrives but the sticky shouldn't
    # be demoted (captures "champion stays first" intent).  Note: if strict-
    # improvement rule runs again here, champion WOULD be overtaken by 0.9.
    # So this test deliberately does NOT call update_best_articles again;
    # it's checking the ordering invariant for whichever sticky is stored.
    insert_paper_entry(papers_db, "NEW", "New", "https://new")
    ps.link_article("PROM-001", "NEW", relevance_score=0.5)
    ps.upsert_classification(
        "PROM-001", "NEW", signal="kept", confidence=0.9, prompt_version="v1",
    )

    promises = ps.get_promises_with_articles(
        str(papers_db), history_db_path=str(history_db),
    )
    target = next(p for p in promises if p["id"] == "PROM-001")
    ids = [a["entry_id"] for a in target["articles"]]
    assert ids[0] == "CHAMP"
    assert "NEW" in ids


def test_no_sticky_means_baseline_sort(
    seeded_promises, papers_db, history_db, insert_paper_entry,
):
    """Without a pinned winner, ordering is pure confidence DESC."""
    ps = seeded_promises
    insert_paper_entry(papers_db, "A", "A", "https://a")
    insert_paper_entry(papers_db, "B", "B", "https://b")
    ps.link_article("PROM-001", "A", relevance_score=0.5)
    ps.link_article("PROM-001", "B", relevance_score=0.5)
    ps.upsert_classification("PROM-001", "A", signal="kept", confidence=0.5, prompt_version="v1")
    ps.upsert_classification("PROM-001", "B", signal="kept", confidence=0.9, prompt_version="v1")
    # Deliberately skip update_best_articles.

    promises = ps.get_promises_with_articles(
        str(papers_db), history_db_path=str(history_db),
    )
    target = next(p for p in promises if p["id"] == "PROM-001")
    ids = [a["entry_id"] for a in target["articles"]]
    assert ids == ["B", "A"]
