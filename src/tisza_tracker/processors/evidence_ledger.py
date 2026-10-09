"""Evidence ledger: derive a promise's status from all of its evidence.

Replaces the sliding vote window.  A status is a pure function of every
post-inauguration signal on record for the promise, so facts do not expire and
a single article cannot flip a status back and forth.

Signals come from :func:`~.llm_classifier.to_signal`:

``kept`` / ``partial``  the promised outcome exists (fully / in part)
``step``                a formal act on the way (bill submitted, decree drafted)
``intent``              officials announce or repeat the plan
``delay``               officials postpone it, or a counterparty blocks it
``reversal``            the government abandons the promise or does the opposite

Rules:

* ``kept`` and ``partially_kept`` need delivery reports from two outlets.
* ``in_progress`` needs one formal step, or an intention reported by two
  outlets.
* ``broken`` is never inferred from tone or from a lapsed deadline.  It needs a
  government reversal reported by two outlets that no later progress
  contradicts, and even then it is only published automatically when
  ``auto_publish_broken`` is on; by default it raises a ``review:`` flag for a
  human to confirm with ``tt promise status ID broken``.
* A lapsed deadline raises a ``review:`` flag.  Absence of linked evidence is
  not evidence of absence, because the matcher misses stories.

Promise ``kind`` adjusts the rules:

``one_off``  a deliverable; done once it exists.
``target``   a measurable outcome due by ``deadline`` (or by the end of the
             term).  It cannot be judged broken before that date, so a reversal
             report only ever raises a review flag.
``ongoing``  a standing commitment ("we will not…", "we keep…").  It is never
             ``kept`` before the term ends; evidence of compliance keeps it
             ``in_progress``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional

PROMISE_KINDS = ("one_off", "target", "ongoing")

# Flags with this prefix ask for a human decision (`tt promise review`).
REVIEW_PREFIX = "review:"


@dataclass
class Assessment:
    """Outcome of weighing one promise's evidence."""

    status: str
    flags: List[str] = field(default_factory=list)
    # Evidence rows the status rests on, oldest first.
    basis: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return any(f.startswith(REVIEW_PREFIX) for f in self.flags)


def promise_kind(promise: Dict[str, Any]) -> str:
    """Return the promise's kind, inferring one when the YAML does not set it.

    A year-only deadline ("2030") marks a measurable target; everything else
    defaults to a one-off deliverable.
    """
    kind = (promise.get("kind") or "").strip().lower()
    if kind in PROMISE_KINDS:
        return kind
    deadline = str(promise.get("deadline") or "").strip()
    if len(deadline) == 4 and deadline.isdigit():
        return "target"
    return "one_off"


def deadline_date(text: Any) -> Optional[date]:
    """Parse a promise deadline: ``"2030"`` means the end of that year."""
    if not text:
        return None
    text = str(text).strip()
    try:
        if len(text) == 4 and text.isdigit():
            return date(int(text), 12, 31)
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _outlet(row: Dict[str, Any]) -> str:
    # Articles of unknown origin cannot corroborate each other.
    return (row.get("outlet") or "").strip().casefold() or "unknown"


def _published(row: Dict[str, Any]) -> str:
    return str(row.get("published") or "")


def assess(
    evidence: Iterable[Dict[str, Any]],
    *,
    deadline: Any = None,
    kind: str = "one_off",
    today: Optional[date] = None,
    min_outlets: int = 2,
    grace_days: int = 30,
    auto_publish_broken: bool = False,
) -> Assessment:
    """Weigh all evidence for one promise.

    *evidence* rows are dicts with ``signal``, ``outlet`` and ``published``
    (``YYYY-MM-DD``); rows whose signal is ``none`` should not be passed in.
    """
    today = today or date.today()
    by: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in evidence:
        by[row.get("signal") or ""].append(row)

    def outlets(*signals: str) -> set:
        return {_outlet(r) for s in signals for r in by[s]}

    def done(status: str, basis: List[Dict[str, Any]]) -> Assessment:
        return Assessment(status, flags, sorted(basis, key=_published))

    flags: List[str] = []
    delivered = by["kept"] + by["partial"]
    due = deadline_date(deadline)

    if by["reversal"]:
        last_reversal = max(_published(r) for r in by["reversal"])
        resumed = [
            r for s in ("kept", "partial", "step") for r in by[s]
            if _published(r) >= last_reversal
        ]
        if resumed:
            flags.append("disputed: reversal report(s) followed by later progress")
        elif len(outlets("reversal")) < min_outlets:
            flags.append(
                f"disputed: {len(by['reversal'])} uncorroborated reversal report(s)"
            )
        else:
            # A target cannot be judged before its date (or the end of the term).
            too_early = kind == "target" and (due is None or today <= due)
            if auto_publish_broken and not too_early:
                return done("broken", by["reversal"])
            flags.append(
                f"{REVIEW_PREFIX} reversal reported by {len(outlets('reversal'))} outlets"
            )

    if (
        kind != "ongoing"
        and due is not None
        and today > due + timedelta(days=grace_days)
        and not delivered
    ):
        flags.append(f"{REVIEW_PREFIX} deadline lapsed with no delivery on record")
    if by["delay"]:
        flags.append("delayed")

    if kind != "ongoing":
        if len(outlets("kept")) >= min_outlets and len(by["kept"]) >= len(by["partial"]):
            return done("kept", by["kept"])
        if len(outlets("kept", "partial")) >= min_outlets:
            return done("partially_kept", delivered)
        if delivered:
            flags.append(f"{REVIEW_PREFIX} single-source delivery report")

    if by["step"] or delivered or len(outlets("intent")) >= min_outlets:
        return done("in_progress", by["step"] + delivered or by["intent"])
    if by["intent"]:
        flags.append("announced only")
    return done("made", [])
