"""
Article full-text fetcher.

Downloads article pages and extracts clean body text using trafilatura.
Results are stored in the dedicated ``article_text.db`` so the main
databases stay lean.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..core.http_client import RetryableHTTPClient

logger = logging.getLogger(__name__)

# Lazy-load trafilatura so import errors are caught gracefully.
_trafilatura = None


def _get_trafilatura():
    global _trafilatura
    if _trafilatura is None:
        try:
            import trafilatura as _traf
            _trafilatura = _traf
        except ImportError:
            logger.error(
                "trafilatura is not installed. "
                "Install it with: pip install trafilatura"
            )
            raise
    return _trafilatura


class ArticleFetcher:
    """Fetch article URLs and extract body text via trafilatura."""

    def __init__(self, *, rps: float = 1.0, timeout: int = 20) -> None:
        self._client = RetryableHTTPClient(rps=rps, max_retries=2, timeout=timeout)

    def fetch_text(self, url: str) -> tuple[Optional[str], str]:
        """Download *url* and extract article text.

        Returns:
            ``(text, status)`` where *status* is one of
            ``'ok'``, ``'failed'``, ``'empty'``.
            *text* is ``None`` when extraction fails.
        """
        try:
            resp = self._client.get_with_retry(url, return_none_on_404=True)
        except Exception as exc:
            logger.warning("HTTP error fetching %s: %s", url, exc)
            return None, "failed"

        if resp is None:
            logger.debug("404 for %s", url)
            return None, "failed"

        traf = _get_trafilatura()
        text = traf.extract(resp.text, favor_recall=True, include_comments=False)

        if not text or not text.strip():
            return None, "empty"

        return text.strip(), "ok"

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
