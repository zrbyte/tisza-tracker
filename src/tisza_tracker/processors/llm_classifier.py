"""LLM-based promise verdict classifier.

Two-pass cascade using an OpenAI-compatible chat-completions endpoint:

1. **Pass 1 — relevance gate** (cheap):  only title + summary are sent.
   Returns ``{relevant: bool, confidence: float, reason: str}``.  An article
   that fails this gate is marked ``irrelevant`` without further work.

2. **Pass 2 — verdict** (expensive):  uses the full article body.  Returns
   ``{verdict, confidence, evidence_quote, reasoning}`` where verdict is one
   of ``kept | in_progress | broken | irrelevant``.

Both passes request JSON output.  Failures are recorded as rows with an
``error`` message so the pipeline can be re-run idempotently.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

VALID_VERDICTS = {"kept", "in_progress", "broken", "irrelevant"}

_PASS1_SYSTEM = (
    "You are a careful Hungarian-language news analyst. "
    "Given a specific government-policy promise and a news article "
    "(title + summary only), decide whether the article substantively "
    "discusses that promise — i.e. its fulfilment, progress, violation, "
    "or debate around it. Articles that merely mention adjacent topics "
    "without discussing the promise itself are NOT relevant. "
    "Respond with strict JSON: "
    '{"relevant": true|false, "confidence": 0.0-1.0, "reason": "short explanation in English"}'
)

_PASS2_SYSTEM = (
    "You are a careful Hungarian-language policy analyst. "
    "Given a specific government-policy promise and the full text of a news "
    "article, classify what the article implies about the promise:\n"
    "  - 'kept': the promise is fulfilled or being implemented successfully.\n"
    "  - 'in_progress': active work, legislation, or partial steps underway.\n"
    "  - 'broken': the promise is violated, reversed, or the opposite is done.\n"
    "  - 'irrelevant': the article does not speak to this promise at all.\n"
    "Quote the single strongest Hungarian sentence from the article as evidence. "
    "Respond with strict JSON: "
    '{"verdict": "kept|in_progress|broken|irrelevant", '
    '"confidence": 0.0-1.0, '
    '"evidence_quote": "verbatim Hungarian sentence from the article (empty if irrelevant)", '
    '"reasoning": "one-sentence English explanation"}'
)


def _trim(text: str, limit: int) -> str:
    if text is None:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def _load_api_key(llm_cfg: Dict[str, Any], secrets_dir: Optional[Path]) -> Optional[str]:
    """Resolve API key from env var or a file under the secrets directory."""
    env_name = llm_cfg.get("api_key_env") or "OPENAI_API_KEY"
    key = os.environ.get(env_name)
    if key:
        return key.strip()

    key_file = llm_cfg.get("api_key_file")
    if key_file:
        path = Path(str(key_file)).expanduser()
        if not path.is_absolute() and secrets_dir is not None:
            path = secrets_dir / path
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    return None


class LLMClassifier:
    """Two-pass OpenAI-compatible classifier."""

    def __init__(
        self,
        llm_cfg: Dict[str, Any],
        secrets_dir: Optional[Path] = None,
    ) -> None:
        from openai import OpenAI  # local import; dep is optional for non-classify flows

        self.model = llm_cfg.get("model") or "gpt-5-nano"
        self.prompt_version = llm_cfg.get("prompt_version") or "v1"
        self.timeout = float(llm_cfg.get("request_timeout") or 30)
        self.max_retries = int(llm_cfg.get("max_retries") or 2)
        self.pass1_enabled = bool(llm_cfg.get("pass1_enabled", True))
        self.pass2_enabled = bool(llm_cfg.get("pass2_enabled", True))

        api_key = _load_api_key(llm_cfg, secrets_dir)
        if not api_key:
            raise RuntimeError(
                "LLM API key not found. Set OPENAI_API_KEY env var or "
                "llm_classification.api_key_file in config."
            )

        base_url = llm_cfg.get("base_url") or os.environ.get("OPENAI_BASE_URL")
        # max_retries=0: we manage retries ourselves (see _chat_json) so we
        # don't stack exponential SDK retries on top of our per-call retries.
        kwargs: Dict[str, Any] = {
            "api_key": api_key,
            "timeout": self.timeout,
            "max_retries": 0,
        }
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)

    # ---- low-level ----

    def _chat_json(self, system: str, user: str) -> Dict[str, Any]:
        """Single JSON-mode chat call with retry on transient errors.

        Retries both network/API errors and JSON-decode errors, with linear
        backoff; the OpenAI SDK's own retry is disabled (see ``__init__``) to
        avoid double-retry stacking.  The last bad-response snippet is kept
        on the exception message for easier debugging.
        """
        last_exc: Optional[Exception] = None
        last_content: Optional[str] = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format={"type": "json_object"},
                )
                last_content = resp.choices[0].message.content
                return json.loads(last_content or "{}")
            except json.JSONDecodeError as exc:
                last_exc = exc
                logger.warning(
                    "LLM returned non-JSON (attempt %d/%d): %s",
                    attempt + 1, self.max_retries + 1, exc,
                )
            except Exception as exc:  # network / API errors
                last_exc = exc
                logger.warning(
                    "LLM call failed (attempt %d/%d): %s",
                    attempt + 1, self.max_retries + 1, exc,
                )
            if attempt < self.max_retries:
                time.sleep(1.5 * (attempt + 1))

        snippet = (last_content or "")[:200]
        raise RuntimeError(
            f"LLM call failed after {self.max_retries + 1} attempts: "
            f"{last_exc}" + (f" | last response: {snippet!r}" if snippet else "")
        )

    # ---- passes ----

    def relevance_gate(
        self,
        promise_text: str,
        article_title: str,
        article_summary: str,
    ) -> Dict[str, Any]:
        user = (
            f"Promise (Hungarian):\n{_trim(promise_text, 500)}\n\n"
            f"Article title: {_trim(article_title, 300)}\n"
            f"Article summary: {_trim(article_summary, 1500)}\n"
        )
        return self._chat_json(_PASS1_SYSTEM, user)

    def verdict(
        self,
        promise_text: str,
        article_title: str,
        article_full_text: str,
        article_summary: str = "",
    ) -> Dict[str, Any]:
        body = article_full_text or article_summary or ""
        user = (
            f"Promise (Hungarian):\n{_trim(promise_text, 500)}\n\n"
            f"Article title: {_trim(article_title, 300)}\n"
            f"Article body:\n{_trim(body, 8000)}\n"
        )
        return self._chat_json(_PASS2_SYSTEM, user)

    # ---- orchestration ----

    def classify(
        self,
        promise_text: str,
        article_title: str,
        article_summary: str,
        article_full_text: Optional[str],
    ) -> Dict[str, Any]:
        """Run the two-pass cascade and return a normalized result dict."""
        result: Dict[str, Any] = {
            "verdict": None,
            "confidence": None,
            "evidence_quote": None,
            "reasoning": None,
            "pass1_relevant": None,
            "pass1_confidence": None,
            "error": None,
            "model": self.model,
            "prompt_version": self.prompt_version,
        }

        # Pass 1: gate
        if self.pass1_enabled:
            try:
                p1 = self.relevance_gate(promise_text, article_title, article_summary)
            except Exception as exc:
                result["error"] = f"pass1: {exc}"
                logger.warning("Pass 1 failed: %s", exc)
                return result

            relevant = bool(p1.get("relevant"))
            result["pass1_relevant"] = relevant
            try:
                result["pass1_confidence"] = float(p1.get("confidence", 0.0))
            except (TypeError, ValueError):
                result["pass1_confidence"] = None

            if not relevant:
                result["verdict"] = "irrelevant"
                result["confidence"] = result["pass1_confidence"]
                result["reasoning"] = p1.get("reason")
                return result

        if not self.pass2_enabled:
            return result

        # Pass 2: verdict
        try:
            p2 = self.verdict(
                promise_text, article_title,
                article_full_text or "", article_summary,
            )
        except Exception as exc:
            result["error"] = f"pass2: {exc}"
            logger.warning("Pass 2 failed: %s", exc)
            return result

        verdict = p2.get("verdict")
        if verdict not in VALID_VERDICTS:
            result["error"] = f"pass2: invalid verdict '{verdict}'"
            return result

        result["verdict"] = verdict
        try:
            result["confidence"] = float(p2.get("confidence", 0.0))
        except (TypeError, ValueError):
            result["confidence"] = None
        result["evidence_quote"] = p2.get("evidence_quote") or None
        result["reasoning"] = p2.get("reasoning") or None
        return result
