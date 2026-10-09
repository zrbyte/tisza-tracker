"""Regression test on the hand-labelled promise-article pairs.

Scores the model outputs recorded with the labels through the current signal
rules, so a change to ``to_signal`` or the quote check that would bring back
false "broken" readings fails here without any API call.  ``tt eval`` runs the
same scoring against the live model.
"""

from __future__ import annotations

import pytest

from tisza_tracker.commands.evaluate import (
    COARSE,
    MIN_AGREEMENT,
    expected_label,
    iter_items,
    load_labelled_set,
    recorded_signal,
    score,
)
from tisza_tracker.core.promise_store import SIGNALS
from tisza_tracker.processors.llm_classifier import (
    ACTORS,
    EVIDENCE_TYPES,
    PROMPT_REVISION,
    government_context,
)


@pytest.fixture(scope="module")
def labelled():
    return load_labelled_set()


@pytest.fixture(scope="module")
def took_office(labelled):
    return government_context(labelled["government"])["took_office"]


@pytest.fixture(scope="module")
def recorded(labelled, took_office):
    return {item["id"]: recorded_signal(item, took_office) for item in iter_items(labelled)}


def test_labelled_set_is_well_formed(labelled):
    items = list(iter_items(labelled))
    assert len(labelled["pairs"]) == 99
    assert len(labelled["synthetic"]) == 8
    assert len({item["id"] for item in items}) == len(items)
    for item in items:
        assert item["promise_id"] in labelled["promises"]
        assert item["gold"] in SIGNALS
        assert set(item["accept"]) <= set(SIGNALS)
        assert item["recorded"]["actor"] in ACTORS
        assert item["recorded"]["evidence_type"] in EVIDENCE_TYPES
        assert item["published"]
    assert set(COARSE) == set(SIGNALS)


def test_recorded_outputs_match_the_current_prompt_revision(labelled):
    """Bumping PROMPT_REVISION means the prompt changed: re-run `tt eval`,
    then refresh the recorded outputs (or this pin) deliberately."""
    assert labelled["recorded_with"]["prompt_revision"] == PROMPT_REVISION


def test_no_real_article_is_read_as_a_broken_promise_beyond_the_known_one(labelled, recorded):
    """All 29 `broken` verdicts of the old prompt were false; one survives."""
    false_reversals = [
        pair["id"] for pair in labelled["pairs"] if recorded[pair["id"]] == "reversal"
    ]
    assert false_reversals == ["5"]


def test_old_broken_verdicts_no_longer_read_as_reversals(labelled, recorded):
    was_broken = [p for p in labelled["pairs"] if p["production_verdict"] == "broken"]
    assert len(was_broken) == 29
    assert sum(recorded[p["id"]] == "reversal" for p in was_broken) == 1


def test_genuine_reversals_are_still_caught(labelled, recorded):
    reversals = [a for a in labelled["synthetic"] if a["gold"] == "reversal"]
    assert len(reversals) == 4
    assert all(recorded[a["id"]] == "reversal" for a in reversals)


def test_opposition_claims_and_expert_opinion_are_not_reversals(labelled, recorded):
    others = [a for a in labelled["synthetic"] if a["gold"] != "reversal"]
    assert len(others) == 4
    assert all(recorded[a["id"]] != "reversal" for a in others)


def test_nothing_before_the_government_took_office_counts(labelled, recorded, took_office):
    early = [p for p in labelled["pairs"] if p["published"] < took_office]
    assert early, "the labelled set should contain pre-inauguration articles"
    assert all(recorded[p["id"]] == "none" for p in early)
    assert all(expected_label({**p, "synthetic": False}, took_office)[0] == "none" for p in early)


def test_agreement_with_the_labels(labelled, recorded):
    result = score(labelled, recorded)
    assert result["scored"] == 107
    assert result["failures"] == []
    assert result["agreement"] >= MIN_AGREEMENT
    # Measured when the rules were written; a drop means a rule got stricter
    # or looser than intended.
    assert result["agreement"] == pytest.approx(98 / 107)


def test_score_reports_failures():
    labelled = {
        "government": {"took_office": "2026-05-12"},
        "pairs": [
            {"id": "1", "promise_id": "P", "title": "t", "published": "2026-06-01",
             "gold": "step", "accept": []},
            {"id": "2", "promise_id": "P", "title": "t", "published": "2026-06-01",
             "gold": "none", "accept": []},
            {"id": "3", "promise_id": "P", "title": "t", "published": "2026-06-01",
             "gold": "none", "accept": []},
        ],
        "synthetic": [
            {"id": "S1", "promise_id": "P", "title": "t", "published": "2026-09-01",
             "gold": "reversal", "accept": []},
        ],
    }
    result = score(labelled, {"1": "reversal", "2": "reversal", "3": "none", "S1": "none"})
    assert result["false_reversals"] == 2
    assert result["reversals_caught"] == 0
    assert len(result["failures"]) == 3
    assert [d["id"] for d in result["disagreements"]] == ["1", "2", "S1"]

    ok = score(labelled, {"1": "intent", "2": "none", "3": "none", "S1": "reversal"})
    assert ok["failures"] == []
    assert ok["agreement"] == 1.0
