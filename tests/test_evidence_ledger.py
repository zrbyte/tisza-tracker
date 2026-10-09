"""Tests for the evidence ledger that turns signals into a promise status."""

from __future__ import annotations

from datetime import date

import pytest

from tisza_tracker.processors.evidence_ledger import (
    assess,
    deadline_date,
    promise_kind,
)

TODAY = date(2026, 10, 9)


def ev(signal: str, outlet: str = "Telex", published: str = "2026-06-10", eid: str = ""):
    return {
        "signal": signal, "outlet": outlet, "published": published,
        "article_entry_id": eid or f"{signal}-{outlet}-{published}",
    }


def status(evidence, **kwargs):
    kwargs.setdefault("today", TODAY)
    return assess(evidence, **kwargs).status


# ---------------------------------------------------------------------------
# kept / partially kept: two outlets
# ---------------------------------------------------------------------------


def test_no_evidence_is_not_started():
    result = assess([], today=TODAY)
    assert result.status == "made"
    assert result.flags == []
    assert result.basis == []


def test_kept_needs_two_outlets():
    assert status([ev("kept", "Telex"), ev("kept", "HVG")]) == "kept"


def test_two_articles_from_one_outlet_do_not_corroborate():
    result = assess(
        [ev("kept", "Telex", "2026-06-10"), ev("kept", "Telex", "2026-06-11")],
        today=TODAY,
    )
    assert result.status == "in_progress"
    assert "review: single-source delivery report" in result.flags


def test_outlet_names_compare_case_insensitively():
    assert status([ev("kept", "Telex"), ev("kept", "telex ")]) == "in_progress"


def test_articles_without_an_outlet_do_not_corroborate_each_other():
    assert status([ev("kept", None, eid="a"), ev("kept", None, eid="b")]) == "in_progress"


def test_partial_delivery_from_two_outlets_is_partially_kept():
    assert status([ev("partial", "Telex"), ev("partial", "HVG")]) == "partially_kept"
    assert status([ev("kept", "Telex"), ev("partial", "HVG")]) == "partially_kept"


def test_more_partial_than_full_reports_is_partially_kept():
    evidence = [
        ev("kept", "Telex"), ev("kept", "HVG"),
        ev("partial", "Index"), ev("partial", "444.hu"), ev("partial", "Portfolio"),
    ]
    assert status(evidence) == "partially_kept"


def test_kept_basis_lists_the_delivery_reports_oldest_first():
    result = assess(
        [ev("kept", "HVG", "2026-07-02"), ev("step", "Index"), ev("kept", "Telex", "2026-07-01")],
        today=TODAY,
    )
    assert result.status == "kept"
    assert [r["outlet"] for r in result.basis] == ["Telex", "HVG"]


# ---------------------------------------------------------------------------
# in progress: one formal step, or an intention from two outlets
# ---------------------------------------------------------------------------


def test_one_formal_step_is_in_progress():
    assert status([ev("step")]) == "in_progress"


def test_single_statement_of_intent_is_not_started():
    result = assess([ev("intent")], today=TODAY)
    assert result.status == "made"
    assert result.flags == ["announced only"]


def test_intent_from_two_outlets_is_in_progress():
    assert status([ev("intent", "Telex"), ev("intent", "HVG")]) == "in_progress"


def test_delay_alone_does_not_start_or_break_a_promise():
    result = assess([ev("delay")], today=TODAY)
    assert result.status == "made"
    assert result.flags == ["delayed"]


# ---------------------------------------------------------------------------
# broken: corroborated reversal, and only via review by default
# ---------------------------------------------------------------------------


def test_single_reversal_report_changes_nothing():
    result = assess([ev("step", published="2026-06-01"), ev("reversal", published="2026-09-01")],
                    today=TODAY)
    assert result.status == "in_progress"
    assert result.flags == ["disputed: 1 uncorroborated reversal report(s)"]
    assert not result.needs_review


def test_corroborated_reversal_goes_to_review_not_to_broken():
    evidence = [
        ev("step", "Index", "2026-06-01"),
        ev("reversal", "Telex", "2026-09-01"), ev("reversal", "HVG", "2026-09-02"),
    ]
    result = assess(evidence, today=TODAY)
    assert result.status == "in_progress"
    assert result.flags == ["review: reversal reported by 2 outlets"]
    assert result.needs_review


def test_corroborated_reversal_is_broken_when_auto_publish_is_on():
    evidence = [ev("reversal", "Telex", "2026-09-01"), ev("reversal", "HVG", "2026-09-02")]
    result = assess(evidence, today=TODAY, auto_publish_broken=True)
    assert result.status == "broken"
    assert len(result.basis) == 2


def test_later_progress_contradicts_a_reversal():
    evidence = [
        ev("reversal", "Telex", "2026-09-01"), ev("reversal", "HVG", "2026-09-02"),
        ev("step", "Index", "2026-09-20"),
    ]
    result = assess(evidence, today=TODAY, auto_publish_broken=True)
    assert result.status == "in_progress"
    assert result.flags == ["disputed: reversal report(s) followed by later progress"]


def test_any_number_of_negative_non_reversal_signals_never_breaks():
    """Tone, delays and opinions are not reversals; only `reversal` counts."""
    evidence = [ev("delay", o) for o in ("Telex", "HVG", "Index", "444.hu")]
    assert status(evidence, auto_publish_broken=True) == "made"


# ---------------------------------------------------------------------------
# deadlines
# ---------------------------------------------------------------------------


def test_lapsed_deadline_raises_a_review_flag_not_broken():
    result = assess([], deadline="2026-06-01", today=TODAY)
    assert result.status == "made"
    assert result.flags == ["review: deadline lapsed with no delivery on record"]


def test_deadline_within_grace_period_is_not_flagged():
    result = assess([], deadline="2026-06-01", today=date(2026, 6, 20))
    assert result.flags == []
    result = assess([], deadline="2026-06-01", today=date(2026, 6, 20), grace_days=7)
    assert result.flags == ["review: deadline lapsed with no delivery on record"]


def test_delivery_on_record_silences_the_deadline_flag():
    result = assess([ev("partial")], deadline="2026-06-01", today=TODAY)
    assert "review: deadline lapsed with no delivery on record" not in result.flags


def test_future_deadline_is_not_flagged():
    assert assess([], deadline="2030", today=TODAY).flags == []


@pytest.mark.parametrize("text,expected", [
    ("2030", date(2030, 12, 31)),
    ("2026-06-01", date(2026, 6, 1)),
    (2027, date(2027, 12, 31)),
    ("", None),
    (None, None),
    ("soon", None),
])
def test_deadline_date(text, expected):
    assert deadline_date(text) == expected


# ---------------------------------------------------------------------------
# promise kinds
# ---------------------------------------------------------------------------


def test_target_cannot_be_broken_before_its_date():
    """A 2030 target cannot be broken in 2026, whatever is reported."""
    evidence = [ev("reversal", "Telex", "2026-09-01"), ev("reversal", "HVG", "2026-09-02")]
    result = assess(evidence, kind="target", deadline="2030", today=TODAY,
                    auto_publish_broken=True)
    assert result.status == "made"
    assert result.flags == ["review: reversal reported by 2 outlets"]

    after = assess(evidence, kind="target", deadline="2030", today=date(2031, 3, 1),
                   auto_publish_broken=True)
    assert after.status == "broken"


def test_target_without_a_date_is_never_broken_automatically():
    evidence = [ev("reversal", "Telex"), ev("reversal", "HVG")]
    assert status(evidence, kind="target", auto_publish_broken=True) == "made"


def test_target_reached_early_is_kept():
    evidence = [ev("kept", "Telex"), ev("kept", "HVG")]
    assert status(evidence, kind="target", deadline="2030") == "kept"


def test_ongoing_commitment_is_never_kept_before_the_term_ends():
    evidence = [ev("kept", "Telex"), ev("kept", "HVG")]
    result = assess(evidence, kind="ongoing", today=TODAY)
    assert result.status == "in_progress"
    assert result.flags == []
    assert len(result.basis) == 2


def test_ongoing_commitment_has_no_deadline_to_lapse():
    assert assess([], kind="ongoing", deadline="2026-06-01", today=TODAY).flags == []


def test_ongoing_commitment_can_still_be_reversed():
    evidence = [ev("reversal", "Telex"), ev("reversal", "HVG")]
    result = assess(evidence, kind="ongoing", today=TODAY)
    assert result.flags == ["review: reversal reported by 2 outlets"]
    assert status(evidence, kind="ongoing", auto_publish_broken=True) == "broken"


@pytest.mark.parametrize("promise,expected", [
    ({"kind": "ongoing"}, "ongoing"),
    ({"kind": "Target"}, "target"),
    ({"kind": None, "deadline": "2030"}, "target"),
    ({"kind": None, "deadline": "2026-06-01"}, "one_off"),
    ({"kind": "nonsense", "deadline": None}, "one_off"),
    ({}, "one_off"),
    ({"kind": "one_off", "deadline": "2027"}, "one_off"),
])
def test_promise_kind(promise, expected):
    assert promise_kind(promise) == expected
