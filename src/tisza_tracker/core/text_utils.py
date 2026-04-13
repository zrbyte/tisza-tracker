"""Shared text processing utilities.

Consolidates text normalization, cleaning, and matching functions used across
the codebase for text fields.
"""

import re
import html as htmllib
import unicodedata
from typing import Optional


def clean_html(text: Optional[str]) -> Optional[str]:
    """Remove HTML tags and unescape entities.

    Args:
        text: Text potentially containing HTML tags

    Returns:
        Cleaned text with tags removed and entities unescaped, or None if input was None
    """
    if not text:
        return text
    text = re.sub(r"<[^>]+>", "", text)
    return htmllib.unescape(text).strip()


def clean_text_for_db(text: Optional[str]) -> Optional[str]:
    """Conservative sanitizer for text before storing in database.

    Removes HTML tags, normalizes whitespace, removes zero-width characters.
    """
    if text is None:
        return None

    s = clean_html(text) or ""

    # Remove zero-width and BOM-like chars
    s = s.replace("\u200B", "").replace("\u200C", "").replace("\u200D", "").replace("\uFEFF", "")
    # Normalize non-breaking spaces
    s = s.replace("\xa0", " ")
    # Remove stray angle brackets
    s = s.replace("<", "").replace(">", "")
    # Collapse excessive whitespace
    s = re.sub(r"[\t\r ]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)

    return s.strip()


def strip_accents(text: str) -> str:
    """Return ASCII-ish text by removing accent marks via Unicode normalization."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(c)
    )


def normalize_name(text: str) -> str:
    """Normalize a human name for loose matching."""
    t = strip_accents(text or "").lower()
    t = re.sub(r"[^a-z\s\-]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t
