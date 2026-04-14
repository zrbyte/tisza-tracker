"""Report command: generate promise tracker table in markdown or HTML."""

from __future__ import annotations

import html as html_mod
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.config import ConfigManager
from ..core.database import DatabaseManager
from ..core.promise_store import PromiseStore
from ..core.paths import resolve_data_path

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


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

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
    # Group by category
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

    # Append any categories not in the predefined order
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
        # Markers not found — try to replace the existing promise tracker section.
        # Look for the first "### Promise tracker" heading and replace everything
        # from there until "### Promise status lifecycle".
        tracker_pattern = re.compile(
            r"(### Promise tracker\n.*?)(### Promise status lifecycle)",
            re.DOTALL,
        )
        match = tracker_pattern.search(content)
        if match:
            # Wrap the new table with markers for future runs.
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


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

STATUS_HTML = {
    "made": '<span class="status status-made">not started</span>',
    "in_progress": '<span class="status status-progress">in progress</span>',
    "kept": '<span class="status status-kept">kept</span>',
    "broken": '<span class="status status-broken">broken</span>',
    "partially_kept": '<span class="status status-partial">partially kept</span>',
    "abandoned": '<span class="status status-abandoned">abandoned</span>',
    "modified": '<span class="status status-modified">modified</span>',
}


def _render_html(promises: List[Dict[str, Any]]) -> str:
    """Render the full promise tracker as a standalone HTML page."""
    by_cat: Dict[str, List[Dict[str, Any]]] = {}
    for p in promises:
        by_cat.setdefault(p["category"], []).append(p)

    total = len(promises)
    with_articles = sum(1 for p in promises if p["articles"])

    body_parts: list[str] = []
    for cat in CATEGORY_ORDER:
        cat_promises = by_cat.get(cat)
        if not cat_promises:
            continue
        heading = html_mod.escape(CATEGORY_HEADINGS.get(cat, cat))
        body_parts.append(f'<h2>{heading}</h2>')
        body_parts.append('<table>')
        body_parts.append(
            '<thead><tr>'
            '<th>ID</th><th>Promise</th><th>Status</th><th>Articles</th>'
            '</tr></thead>'
        )
        body_parts.append('<tbody>')
        for p in cat_promises:
            pid = html_mod.escape(p["id"])
            text = html_mod.escape(p["text"])
            status_html = STATUS_HTML.get(p["current_status"], html_mod.escape(p["current_status"]))
            art_items = []
            for a in p["articles"]:
                t = html_mod.escape(a["title"])
                if len(t) > 80:
                    t = t[:77] + "..."
                verdict = a.get("verdict") or ""
                badge = ""
                if verdict in {"kept", "in_progress", "broken"}:
                    badge = (
                        f'<span class="v v-{verdict}" '
                        f'title="{html_mod.escape(verdict)}">'
                        f'{_VERDICT_BADGE_MD[verdict]}</span> '
                    )
                link_html = (
                    f'{badge}<a href="{html_mod.escape(a["link"])}" target="_blank" '
                    f'rel="noopener noreferrer">{t}</a>'
                )
                quote = (a.get("evidence_quote") or "").strip()
                if quote:
                    if len(quote) > 220:
                        quote = quote[:217] + "..."
                    link_html += (
                        f' <span class="quote">&mdash; &ldquo;'
                        f'{html_mod.escape(quote)}&rdquo;</span>'
                    )
                art_items.append(f"<li>{link_html}</li>")
            articles_html = f"<ul>{''.join(art_items)}</ul>" if art_items else ""
            body_parts.append(
                f'<tr><td>{pid}</td><td>{text}</td>'
                f'<td>{status_html}</td><td>{articles_html}</td></tr>'
            )
        body_parts.append('</tbody></table>')

    import datetime as _dt
    date_str = _dt.date.today().isoformat()
    body_html = "\n".join(body_parts)

    return f"""<!DOCTYPE html>
<html lang="hu">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tisza Tracker — Promise Report</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         margin: 2rem auto; max-width: 1200px; padding: 0 1rem; color: #222; }}
  h1 {{ border-bottom: 2px solid #1a73e8; padding-bottom: .4rem; }}
  h2 {{ margin-top: 2rem; color: #1a73e8; }}
  .summary {{ color: #555; margin-bottom: 1.5rem; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 1.5rem; }}
  th, td {{ border: 1px solid #ddd; padding: .5rem .75rem; text-align: left; vertical-align: top; }}
  th {{ background: #f5f7fa; }}
  tr:nth-child(even) {{ background: #fafbfc; }}
  td:first-child {{ white-space: nowrap; font-family: monospace; }}
  td:nth-child(3) {{ white-space: nowrap; }}
  a {{ color: #1a73e8; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .status {{ padding: .15rem .5rem; border-radius: 3px; font-size: .85rem; }}
  .status-made {{ background: #e8eaed; color: #555; }}
  .status-progress {{ background: #fef7e0; color: #8a6d00; }}
  .status-kept {{ background: #e6f4ea; color: #1e7e34; }}
  .status-broken {{ background: #fce8e6; color: #c5221f; }}
  .status-partial {{ background: #fff3cd; color: #856404; }}
  .status-abandoned {{ background: #f8d7da; color: #721c24; }}
  .status-modified {{ background: #d1ecf1; color: #0c5460; }}
  td ul {{ margin: 0; padding-left: 1rem; }}
  td li {{ margin-bottom: .25rem; }}
  .quote {{ color: #555; font-style: italic; font-size: .9em; }}
  .v {{ display: inline-block; width: 1.1em; font-weight: bold; }}
  .v-kept {{ color: #1e7e34; }}
  .v-in_progress {{ color: #8a6d00; }}
  .v-broken {{ color: #c5221f; }}
</style>
</head>
<body>
<h1>Tisza Tracker — Promise Report</h1>
<p class="summary">{total} promises tracked, {with_articles} with matched articles. Generated {date_str}.</p>
{body_html}
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(
    config_path: str,
    fmt: str = "md",
    readme: Optional[str] = None,
    output: Optional[str] = None,
) -> Optional[str]:
    """Generate promise tracker report.

    Args:
        config_path: Path to config file.
        fmt: Output format — "md" or "html".
        readme: If set, update the README at this path (md format only).
        output: If set, write output to this file instead of stdout.

    Returns:
        The rendered report string (for ``--json`` or programmatic use).
    """
    promises = _load_promises(config_path)
    logger.info("Loaded %d promises for report", len(promises))

    if fmt == "html":
        rendered = _render_html(promises)
        if not output:
            output = str(resolve_data_path("html", "promise_report.html", ensure_parent=True))
        Path(output).write_text(rendered, encoding="utf-8")
        logger.info("Wrote HTML report to %s", output)
        return rendered

    # Markdown
    rendered = _render_md(promises)
    if readme:
        _update_readme(rendered, Path(readme))
    if output:
        Path(output).write_text(rendered, encoding="utf-8")
        logger.info("Wrote markdown report to %s", output)
    elif not readme:
        # Print to stdout if no file targets given
        print(rendered)
    return rendered
