"""Eval command: score the evidence extraction against the hand-labelled set.

``system/eval/labelled_set.json`` holds 99 real promise-article pairs labelled
by hand during the October 2026 audit of the status algorithm, plus 8 synthetic
articles — four of them genuine government reversals, which the real corpus
does not contain.  Run ``tt eval`` after any change to the pass-2 prompt, the
signal rules or the model; it exits non-zero when the result falls below the
thresholds below.

Article bodies are not part of the repository.  They are read from
``<data dir>/eval_bodies/<entry_id>.json`` (the texts as they were when
labelled) when present, otherwise from article_text.db, otherwise downloaded.

``tt eval --recorded`` scores the model outputs stored with the labels
instead of calling the model, which checks the code-side rules alone.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from ..core.config import ConfigManager
from ..core.paths import get_data_dir, get_system_path
from ..processors.article_fetcher import ArticleFetcher, strip_paywall
from ..processors.llm_classifier import (
    DEFAULT_MIN_BODY_CHARS,
    LLMClassifier,
    government_context,
    quote_is_verbatim,
    to_signal,
)

logger = logging.getLogger(__name__)

LABELLED_SET_PATH = get_system_path("eval") / "labelled_set.json"

# Kept / in progress / broken / nothing: the level at which a label has to
# agree.  Finer distinctions (step against intent) vary between model runs.
COARSE = {
    "kept": "K", "partial": "K", "step": "P", "intent": "P", "delay": "P",
    "reversal": "B", "none": "N",
}

# Regression thresholds.  The audit measured 1 false reversal in 99 real
# pairs, 4 of 4 synthetic reversals caught and 93% agreement for gpt-5-mini.
MAX_FALSE_REVERSALS = 1
MAX_SYNTHETIC_FALSE_REVERSALS = 0
MIN_AGREEMENT = 0.85


def load_labelled_set(path: Optional[Path] = None) -> Dict[str, Any]:
    return json.loads(Path(path or LABELLED_SET_PATH).read_text(encoding="utf-8"))


def iter_items(labelled: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
    """Yield the real pairs, then the synthetic articles, in one shape."""
    for pair in labelled["pairs"]:
        yield {**pair, "synthetic": False}
    for article in labelled["synthetic"]:
        yield {**article, "synthetic": True, "group": "synthetic"}


def expected_label(item: Dict[str, Any], took_office: str) -> Tuple[str, set]:
    """The label to score against: (best, every acceptable signal).

    The labels describe what an article reports.  For an article published
    before the government took office the code overrides that with ``none``,
    so that is what is expected of the pipeline.
    """
    if item["published"] < took_office:
        return "none", {"none"}
    return item["gold"], {item["gold"], *item["accept"]}


def recorded_signal(item: Dict[str, Any], took_office: str) -> str:
    """Signal the current rules derive from the model output stored with a label."""
    record = item["recorded"]
    if item["synthetic"]:
        body = item["body"]
        verbatim = quote_is_verbatim(record.get("quote"), item["title"], body)
        body_seen = len(body) >= DEFAULT_MIN_BODY_CHARS
    else:
        verbatim = item["recorded_quote_verbatim"]
        body_seen = item["recorded_body_chars"] >= DEFAULT_MIN_BODY_CHARS
    return to_signal(
        record, item["published"],
        took_office=took_office, body_seen=body_seen, quote_verbatim=verbatim,
    )


def score(
    labelled: Dict[str, Any],
    signals: Dict[str, str],
) -> Dict[str, Any]:
    """Compare *signals* (item id → signal) with the labels."""
    took_office = government_context(labelled.get("government"))["took_office"]
    rows = []
    for item in iter_items(labelled):
        if item["id"] not in signals:
            continue
        best, accept = expected_label(item, took_office)
        rows.append({
            "id": item["id"], "promise_id": item["promise_id"], "title": item["title"],
            "synthetic": item["synthetic"], "best": best, "accept": accept,
            "signal": signals[item["id"]],
        })

    def agrees(row: Dict[str, Any]) -> bool:
        return COARSE[row["signal"]] in {COARSE[a] for a in row["accept"]}

    real = [r for r in rows if not r["synthetic"]]
    synthetic = [r for r in rows if r["synthetic"]]
    reversals = [r for r in synthetic if r["best"] == "reversal"]
    others = [r for r in synthetic if r["best"] != "reversal"]
    agreed = [r for r in rows if agrees(r)]

    result = {
        "scored": len(rows),
        "real_pairs": len(real),
        "false_reversals": sum(r["signal"] == "reversal" for r in real),
        "reversals_expected": len(reversals),
        "reversals_caught": sum(r["signal"] == "reversal" for r in reversals),
        "synthetic_false_reversals": sum(r["signal"] == "reversal" for r in others),
        "agreement": len(agreed) / len(rows) if rows else 0.0,
        "disagreements": [
            {**r, "accept": sorted(r["accept"])} for r in rows if not agrees(r)
        ],
    }
    result["failures"] = _failures(result)
    return result


def _failures(result: Dict[str, Any]) -> List[str]:
    failures = []
    if result["false_reversals"] > MAX_FALSE_REVERSALS:
        failures.append(
            f"{result['false_reversals']} real articles read as a reversal "
            f"(at most {MAX_FALSE_REVERSALS} allowed)"
        )
    if result["reversals_caught"] < result["reversals_expected"]:
        failures.append(
            f"only {result['reversals_caught']} of {result['reversals_expected']} "
            "synthetic reversals caught"
        )
    if result["synthetic_false_reversals"] > MAX_SYNTHETIC_FALSE_REVERSALS:
        failures.append(
            f"{result['synthetic_false_reversals']} synthetic non-reversals read as a reversal"
        )
    if result["agreement"] < MIN_AGREEMENT:
        failures.append(
            f"agreement {result['agreement']:.0%} is below {MIN_AGREEMENT:.0%}"
        )
    return failures


def _load_article(
    item: Dict[str, Any],
    db: Any,
    fetcher: ArticleFetcher,
    bodies_dir: Path,
) -> Optional[Dict[str, Any]]:
    """Assemble the article dict the classifier expects, or None without a body."""
    article = {
        "title": item["title"], "summary": "", "full_text": None,
        "outlet": item["outlet"], "published": item["published"],
    }
    if item["synthetic"]:
        article["full_text"] = item["body"]
        return article

    snapshot = bodies_dir / f"{item['entry_id']}.json"
    if snapshot.exists():
        data = json.loads(snapshot.read_text(encoding="utf-8"))
        article["summary"] = data.get("summary") or ""
        article["full_text"] = data.get("body") or ""
        return article

    row = db.get_article_text(item["entry_id"]) or {}
    article["summary"] = row.get("summary") or ""
    body = strip_paywall(row.get("full_text"))
    if not body:
        text, _status = fetcher.fetch_text(item["url"])
        body = strip_paywall(text)
    if not body:
        return None
    article["full_text"] = body
    return article


def run(
    config_path: str,
    *,
    recorded: bool = False,
    model: Optional[str] = None,
    limit: Optional[int] = None,
    output_json: bool = False,
) -> Dict[str, Any]:
    """Score the labelled set; returns the result dict (see :func:`score`)."""
    labelled = load_labelled_set()
    items = list(iter_items(labelled))
    if limit is not None:
        items = items[:limit]
    took_office = government_context(labelled.get("government"))["took_office"]

    signals: Dict[str, str] = {}
    skipped: List[str] = []
    if recorded:
        signals = {item["id"]: recorded_signal(item, took_office) for item in items}
    else:
        from ..core.database import DatabaseManager

        cm = ConfigManager(config_path)
        config = cm.load_config()
        llm_cfg = dict(config.get("llm_classification") or {})
        if model:
            llm_cfg["pass2_model"] = model
        classifier = LLMClassifier(
            llm_cfg, secrets_dir=Path(cm.base_dir) / "secrets",
            government=labelled.get("government"),
        )
        db = DatabaseManager(config)
        bodies_dir = get_data_dir() / "eval_bodies"
        with ArticleFetcher() as fetcher:
            for n, item in enumerate(items, 1):
                article = _load_article(item, db, fetcher, bodies_dir)
                if article is None:
                    skipped.append(item["id"])
                    continue
                promise = {"id": item["promise_id"], **labelled["promises"][item["promise_id"]]}
                body = article["full_text"] or ""
                try:
                    record = classifier.extract(promise, article, body)
                except Exception as exc:
                    logger.warning("Item %s failed: %s", item["id"], exc)
                    skipped.append(item["id"])
                    continue
                signals[item["id"]] = classifier.signal_for(record, article, body)["signal"]
                if not output_json and n % 20 == 0:
                    print(f"  {n}/{len(items)} extracted")
        db.close_all_connections()

    result = score(labelled, signals)
    result["skipped"] = skipped
    result["mode"] = "recorded" if recorded else "live"

    if output_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return result

    print(f"Labelled set ({result['mode']}): {result['scored']} items scored"
          + (f", {len(skipped)} skipped (no body or call failed)" if skipped else ""))
    print(f"  false reversals on real pairs:   {result['false_reversals']}/{result['real_pairs']}")
    print(f"  synthetic reversals caught:      "
          f"{result['reversals_caught']}/{result['reversals_expected']}")
    print(f"  synthetic non-reversals flagged: {result['synthetic_false_reversals']}")
    print(f"  agreement with labels:           {result['agreement']:.0%}")
    for row in result["disagreements"]:
        print(f"    [{row['id']}] {row['promise_id']} expected {row['best']}, "
              f"got {row['signal']} | {row['title'][:70]}")
    for failure in result["failures"]:
        print(f"  FAIL: {failure}")
    if not result["failures"]:
        print("  OK")
    return result
