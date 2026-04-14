"""Tests for report.py rendering — article markdown + HTML."""

from __future__ import annotations

from tisza_tracker.commands.report import (
    _VERDICT_BADGE_MD,
    _article_md,
    _render_md,
    _render_html,
)


# ---------------------------------------------------------------------------
# _article_md
# ---------------------------------------------------------------------------


def test_article_md_no_verdict_no_quote():
    article = {"title": "Headline", "link": "https://example.com/a"}
    assert _article_md(article) == "[Headline](https://example.com/a)"


def test_article_md_with_verdict_badge():
    article = {
        "title": "Headline", "link": "https://example.com/a",
        "verdict": "kept",
    }
    out = _article_md(article)
    assert out.startswith(f"{_VERDICT_BADGE_MD['kept']} ")
    assert "[Headline](https://example.com/a)" in out


def test_article_md_irrelevant_badge_not_rendered():
    """Irrelevant verdicts have no visible badge (they shouldn't reach the
    renderer anyway, but guard the code)."""
    article = {
        "title": "T", "link": "https://x",
        "verdict": "irrelevant",
    }
    out = _article_md(article)
    assert "[T](https://x)" in out
    assert not out.startswith("✓") and not out.startswith("→") and not out.startswith("✗")


def test_article_md_with_evidence_quote():
    article = {
        "title": "T", "link": "https://x",
        "verdict": "in_progress",
        "evidence_quote": "A Hungarian sentence.",
    }
    out = _article_md(article)
    assert '— "A Hungarian sentence."' in out


def test_article_md_truncates_long_title():
    article = {"title": "X" * 120, "link": "https://x"}
    out = _article_md(article)
    # Title gets cut at 77 chars + ellipsis
    assert out.count("X") == 77
    assert "..." in out


def test_article_md_truncates_long_quote():
    article = {
        "title": "T", "link": "https://x",
        "verdict": "kept",
        "evidence_quote": "X" * 300,
    }
    out = _article_md(article)
    quoted_part = out.split('"')[1]
    assert len(quoted_part) <= 140
    assert quoted_part.endswith("...")


def test_article_md_escapes_pipes_in_quote():
    """Pipes break markdown tables; they must be escaped in both title and quote."""
    article = {
        "title": "A | B", "link": "https://x",
        "verdict": "kept",
        "evidence_quote": "quote | with | pipes",
    }
    out = _article_md(article)
    assert "A \\| B" in out
    assert "quote \\| with \\| pipes" in out


def test_article_md_collapses_newlines_in_quote():
    article = {
        "title": "T", "link": "https://x",
        "verdict": "kept",
        "evidence_quote": "line one\nline two",
    }
    out = _article_md(article)
    assert "\n" not in out.split("—", 1)[1]


# ---------------------------------------------------------------------------
# _render_md — category grouping + legend
# ---------------------------------------------------------------------------


def _promise(pid: str, category: str = "gazdasag", articles=None, status: str = "made"):
    return {
        "id": pid,
        "text": f"{pid} text",
        "category": category,
        "current_status": status,
        "articles": articles or [],
    }


def test_render_md_header_and_legend():
    out = _render_md([_promise("P1")])
    assert "### Promise tracker" in out
    assert "Status legend:" in out
    assert "Article badges:" in out  # audit follow-up


def test_render_md_groups_by_category():
    promises = [
        _promise("P1", category="gazdasag"),
        _promise("P2", category="oktatas"),
    ]
    out = _render_md(promises)
    # Category ordering: gazdasag before oktatas per CATEGORY_ORDER
    assert out.index("Gazdasag") < out.index("Oktatas")


def test_render_md_shows_promise_row():
    promises = [
        _promise(
            "P1",
            articles=[{
                "title": "Art", "link": "https://a",
                "verdict": "kept", "confidence": 0.9,
                "evidence_quote": "q",
            }],
        ),
    ]
    out = _render_md(promises)
    assert "| P1 | P1 text |" in out
    assert "[Art](https://a)" in out


def test_render_md_escapes_promise_text_pipes():
    promises = [_promise("P1")]
    promises[0]["text"] = "text | with | pipes"
    out = _render_md(promises)
    assert "text \\| with \\| pipes" in out


def test_render_md_unknown_category_still_rendered():
    """Categories outside CATEGORY_ORDER should still produce a section."""
    promises = [_promise("P1", category="brand-new-category")]
    out = _render_md(promises)
    assert "brand-new-category" in out
    assert "| P1 |" in out


# ---------------------------------------------------------------------------
# _render_html
# ---------------------------------------------------------------------------


def test_render_html_contains_verdict_class():
    promises = [
        _promise(
            "P1",
            articles=[{
                "title": "T", "link": "https://x",
                "verdict": "broken", "confidence": 0.8,
                "evidence_quote": "",
            }],
        ),
    ]
    out = _render_html(promises)
    assert 'class="v v-broken"' in out
    assert _VERDICT_BADGE_MD["broken"] in out


def test_render_html_escapes_user_content():
    """HTML injection guard — a malicious title must be escaped."""
    promises = [
        _promise(
            "P1",
            articles=[{
                "title": "<script>alert(1)</script>",
                "link": "https://x",
                "verdict": "kept",
            }],
        ),
    ]
    out = _render_html(promises)
    assert "<script>alert" not in out
    assert "&lt;script&gt;" in out


def test_render_html_no_badge_for_unclassified():
    promises = [
        _promise(
            "P1",
            articles=[{"title": "T", "link": "https://x"}],
        ),
    ]
    out = _render_html(promises)
    # Unclassified articles should not produce a verdict span
    assert 'class="v v-' not in out


def test_render_html_empty_articles_produces_empty_cell():
    promises = [_promise("P1")]
    out = _render_html(promises)
    # Row should exist but articles cell is empty (no <ul>)
    assert "<td>P1</td>" in out
    assert "<ul>" not in out.split("P1")[1].split("</tr>")[0]
