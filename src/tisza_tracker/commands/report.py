"""Report command: generate the promise tracker markdown table."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.config import ConfigManager
from ..core.database import DatabaseManager
from ..core.promise_store import PromiseStore

logger = logging.getLogger(__name__)

# Display names for promise categories (DB key → heading).
CATEGORY_HEADINGS: Dict[str, str] = {
    "gazdasag": "Gazdasag (economy, tax, budget, agriculture)",
    "korrupcio": "Korrupcio (anti-corruption, transparency)",
    "igazsagszolgaltatas": "Igazsagszolgaltatas (rule of law, justice, civil society)",
    "egeszsegugy": "Egeszsegugy (healthcare)",
    "oktatas": "Oktatas (education, culture)",
    "szocialis": "Szocialis (pensions, child protection, family, equality)",
    "kozlekedes": "Kozlekedes (transport, energy, housing)",
    "kornyezetvedelem": "Kornyezetvedelem (environment, waste, water, animal welfare)",
    "kulpolitika": "Kulpolitika (foreign policy)",
    "altalanos": "Altalanos (general, defence, migration, demographics, digital)",
}

# Rendering order for categories.
CATEGORY_ORDER = [
    "gazdasag",
    "korrupcio",
    "igazsagszolgaltatas",
    "egeszsegugy",
    "oktatas",
    "szocialis",
    "kozlekedes",
    "kornyezetvedelem",
    "kulpolitika",
    "altalanos",
]

STATUS_EMOJI = {
    "made": ":black_square_button:",
    "in_progress": ":hourglass_flowing_sand:",
    "kept": ":white_check_mark:",
    "broken": ":x:",
    "partially_kept": ":yellow_circle:",
    "abandoned": ":no_entry_sign:",
    "modified": ":arrows_counterclockwise:",
}


def _load_promises(config_path: str) -> List[Dict[str, Any]]:
    """Load promises with enriched article data from the databases."""
    cm = ConfigManager(config_path)
    config = cm.load_config()
    db = DatabaseManager(config)
    ps = PromiseStore(config)
    papers_path = db.db_paths["current"]
    history_path = db.db_paths["history"]

    llm_cfg = config.get("llm_classification") or {}
    top_n = llm_cfg.get("top_n_in_report")
    if top_n is not None:
        try:
            top_n = int(top_n)
        except (TypeError, ValueError):
            top_n = None

    promises = ps.get_promises_with_articles(
        papers_path,
        history_db_path=history_path,
        max_per_promise=top_n,
    )
    db.close_all_connections()
    return promises


_VERDICT_BADGE_MD = {
    "kept": "✓",
    "in_progress": "→",
    "broken": "✗",
}


def _article_md(article: Dict[str, Any]) -> str:
    """Render a single article as a markdown link with optional evidence."""
    title = article["title"]
    if len(title) > 80:
        title = title[:77] + "..."
    title = title.replace("|", "\\|")
    link_md = f"[{title}]({article['link']})"

    verdict = article.get("verdict")
    badge = _VERDICT_BADGE_MD.get(verdict or "")
    if badge:
        link_md = f"{badge} {link_md}"

    quote = (article.get("evidence_quote") or "").strip()
    if quote:
        if len(quote) > 140:
            quote = quote[:137] + "..."
        quote = quote.replace("|", "\\|").replace("\n", " ")
        link_md = f'{link_md} — "{quote}"'
    return link_md


def _render_md(promises: List[Dict[str, Any]]) -> str:
    """Render the full promise tracker as markdown."""
    by_cat: Dict[str, List[Dict[str, Any]]] = {}
    for p in promises:
        by_cat.setdefault(p["category"], []).append(p)

    lines: list[str] = []
    lines.append("### Promise tracker")
    lines.append("")
    lines.append(
        "Status legend: :white_check_mark: kept | :hourglass_flowing_sand: in progress "
        "| :x: broken | :black_square_button: not yet started"
    )
    lines.append("")
    lines.append(
        "Article badges: ✓ kept | → in progress | ✗ broken "
        "(LLM verdict; evidence quote in italics)"
    )

    for cat in CATEGORY_ORDER:
        cat_promises = by_cat.get(cat)
        if not cat_promises:
            continue
        heading = CATEGORY_HEADINGS.get(cat, cat)
        lines.append("")
        lines.append(f"### {heading}")
        lines.append("")
        lines.append("| ID | Promise | Status | Articles |")
        lines.append("|---|---|---|---|")
        for p in cat_promises:
            status = STATUS_EMOJI.get(p["current_status"], p["current_status"])
            articles = ", ".join(_article_md(a) for a in p["articles"])
            text = p["text"].replace("|", "\\|")
            lines.append(f"| {p['id']} | {text} | {status} | {articles} |")

    for cat, cat_promises in by_cat.items():
        if cat in CATEGORY_ORDER:
            continue
        heading = CATEGORY_HEADINGS.get(cat, cat)
        lines.append("")
        lines.append(f"### {heading}")
        lines.append("")
        lines.append("| ID | Promise | Status | Articles |")
        lines.append("|---|---|---|---|")
        for p in cat_promises:
            status = STATUS_EMOJI.get(p["current_status"], p["current_status"])
            articles = ", ".join(_article_md(a) for a in p["articles"])
            text = p["text"].replace("|", "\\|")
            lines.append(f"| {p['id']} | {text} | {status} | {articles} |")

    lines.append("")
    return "\n".join(lines)


def _update_readme(md_table: str, readme_path: Path) -> None:
    """Replace the promise tracker section in the README between markers."""
    start_marker = "<!-- PROMISES_START -->"
    end_marker = "<!-- PROMISES_END -->"

    content = readme_path.read_text(encoding="utf-8")

    if start_marker in content and end_marker in content:
        pattern = re.compile(
            re.escape(start_marker) + r".*?" + re.escape(end_marker),
            re.DOTALL,
        )
        replacement = f"{start_marker}\n{md_table}\n{end_marker}"
        new_content = pattern.sub(replacement, content)
    else:
        tracker_pattern = re.compile(
            r"(### Promise tracker\n.*?)(### Promise status lifecycle)",
            re.DOTALL,
        )
        match = tracker_pattern.search(content)
        if match:
            replacement = (
                f"{start_marker}\n{md_table}\n{end_marker}\n\n"
                f"{match.group(2)}"
            )
            new_content = content[: match.start()] + replacement + content[match.end():]
        else:
            logger.warning(
                "Could not find promise tracker section in README. "
                "Add %s / %s markers and re-run.", start_marker, end_marker,
            )
            return

    readme_path.write_text(new_content, encoding="utf-8")
    logger.info("Updated promise tracker in %s", readme_path)


def run(
    config_path: str,
    readme: Optional[str] = None,
    output: Optional[str] = None,
) -> Optional[str]:
    """Generate the promise tracker markdown report.

    Args:
        config_path: Path to config file.
        readme: If set, update the README at this path.
        output: If set, write the markdown to this file (otherwise stdout
            unless a README target is given).

    Returns:
        The rendered markdown (for programmatic use).
    """
    promises = _load_promises(config_path)
    logger.info("Loaded %d promises for report", len(promises))

    rendered = _render_md(promises)
    if readme:
        _update_readme(rendered, Path(readme))
    if output:
        Path(output).write_text(rendered, encoding="utf-8")
        logger.info("Wrote markdown report to %s", output)
    elif not readme:
        print(rendered)
    return rendered
