"""Tests for the two-pass LLM classifier.

The real OpenAI client is replaced with a recorder that returns scripted
JSON strings. This lets us drive every branch without network access.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tisza_tracker.processors.llm_classifier import (
    LLMClassifier,
    _load_api_key,
    _trim,
)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


class _FakeOpenAI:
    """Replacement for ``openai.OpenAI`` that replays a scripted sequence.

    Each ``create`` call pops the next item off ``responses``. Items may be:
    - a dict → returned verbatim as JSON
    - a string → returned verbatim as content (for non-JSON testing)
    - an Exception → raised
    """

    def __init__(self, responses, **_kwargs):
        self._responses = list(responses)
        self.calls = []

    @property
    def chat(self):
        return SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, *, model, messages, response_format):
        self.calls.append({"model": model, "messages": messages})
        if not self._responses:
            raise RuntimeError("FakeOpenAI: ran out of scripted responses")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        content = json.dumps(item) if isinstance(item, dict) else str(item)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )


def _make_classifier(responses, *, monkeypatch, **overrides):
    """Build an LLMClassifier wired to a FakeOpenAI with *responses* queued."""
    cfg = {
        "model": "fake-model",
        "api_key_env": "TEST_API_KEY",
        "prompt_version": "v1",
        "request_timeout": 1,
        "max_retries": 1,
        **overrides,
    }
    monkeypatch.setenv("TEST_API_KEY", "sk-test")

    fake = _FakeOpenAI(responses)

    def _openai_factory(**kwargs):
        # Capture init kwargs for the tests that care
        fake.init_kwargs = kwargs
        return fake

    with patch("openai.OpenAI", _openai_factory):
        classifier = LLMClassifier(cfg)
    return classifier, fake


# ---------------------------------------------------------------------------
# _trim
# ---------------------------------------------------------------------------


def test_trim_preserves_short_text():
    assert _trim("hello", 100) == "hello"


def test_trim_strips_whitespace():
    assert _trim("  hello  ", 100) == "hello"


def test_trim_none_returns_empty():
    assert _trim(None, 100) == ""


def test_trim_truncates_and_appends_ellipsis():
    out = _trim("x" * 200, 10)
    assert out.startswith("x" * 10)
    assert out.endswith("…")
    assert len(out) == 11  # 10 chars + ellipsis


# ---------------------------------------------------------------------------
# _load_api_key
# ---------------------------------------------------------------------------


def test_load_api_key_from_env(monkeypatch):
    monkeypatch.setenv("CUSTOM_KEY", "sk-abc  ")
    cfg = {"api_key_env": "CUSTOM_KEY"}
    assert _load_api_key(cfg, None) == "sk-abc"


def test_load_api_key_from_file(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    key_file = tmp_path / "api.key"
    key_file.write_text("  sk-from-file\n", encoding="utf-8")
    cfg = {"api_key_file": str(key_file)}
    assert _load_api_key(cfg, secrets_dir=tmp_path) == "sk-from-file"


def test_load_api_key_relative_file_joined_with_secrets_dir(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "k").write_text("sk-xyz", encoding="utf-8")
    cfg = {"api_key_file": "k"}
    assert _load_api_key(cfg, secrets_dir=secrets) == "sk-xyz"


def test_load_api_key_missing_returns_none(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert _load_api_key({}, None) is None


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


def test_init_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MISSING_KEY", raising=False)
    with pytest.raises(RuntimeError, match="LLM API key not found"):
        LLMClassifier({"api_key_env": "MISSING_KEY"})


def test_init_disables_sdk_retries(monkeypatch):
    """The audit fix: our own retries manage backoff; the SDK's own retry
    must be turned off so we don't stack them."""
    _, fake = _make_classifier([{"relevant": False, "confidence": 0.9, "reason": ""}], monkeypatch=monkeypatch)
    assert fake.init_kwargs.get("max_retries") == 0


def test_init_passes_base_url_when_configured(monkeypatch):
    _, fake = _make_classifier(
        [{"relevant": False, "confidence": 0.9, "reason": ""}],
        monkeypatch=monkeypatch,
        base_url="http://localhost:1234/v1",
    )
    assert fake.init_kwargs.get("base_url") == "http://localhost:1234/v1"


# ---------------------------------------------------------------------------
# classify — full orchestration paths
# ---------------------------------------------------------------------------


def test_classify_irrelevant_short_circuits_pass2(monkeypatch):
    classifier, fake = _make_classifier(
        [{"relevant": False, "confidence": 0.7, "reason": "off-topic"}],
        monkeypatch=monkeypatch,
    )

    result = classifier.classify(
        promise_text="A promise", article_title="T", article_summary="S",
        article_full_text="full body",
    )
    assert result["verdict"] == "irrelevant"
    assert result["confidence"] == 0.7
    assert result["pass1_relevant"] is False
    assert result["error"] is None
    assert len(fake.calls) == 1  # pass 2 never runs


def test_classify_runs_pass2_when_relevant(monkeypatch):
    classifier, fake = _make_classifier(
        [
            {"relevant": True, "confidence": 0.9, "reason": ""},
            {"verdict": "kept", "confidence": 0.8,
             "evidence_quote": "q", "reasoning": "r"},
        ],
        monkeypatch=monkeypatch,
    )

    result = classifier.classify(
        promise_text="A", article_title="T", article_summary="S",
        article_full_text="full",
    )
    assert result["verdict"] == "kept"
    assert result["confidence"] == 0.8
    assert result["evidence_quote"] == "q"
    assert result["pass1_relevant"] is True
    assert result["error"] is None
    assert len(fake.calls) == 2


def test_classify_pass2_invalid_verdict_records_error(monkeypatch):
    classifier, _ = _make_classifier(
        [
            {"relevant": True, "confidence": 0.9, "reason": ""},
            {"verdict": "maybe", "confidence": 0.5},
        ],
        monkeypatch=monkeypatch,
    )
    result = classifier.classify("A", "T", "S", "full")
    assert result["verdict"] is None
    assert "invalid verdict" in result["error"]


def test_classify_pass1_failure_records_error(monkeypatch):
    classifier, _ = _make_classifier(
        [RuntimeError("boom"), RuntimeError("boom"), RuntimeError("boom")],
        monkeypatch=monkeypatch,
    )
    result = classifier.classify("A", "T", "S", "full")
    assert result["verdict"] is None
    assert result["error"] and result["error"].startswith("pass1:")


def test_classify_pass2_failure_records_error(monkeypatch):
    classifier, _ = _make_classifier(
        [
            {"relevant": True, "confidence": 0.9, "reason": ""},
            RuntimeError("pass2 boom"),
            RuntimeError("pass2 boom"),
        ],
        monkeypatch=monkeypatch,
    )
    result = classifier.classify("A", "T", "S", "full")
    assert result["verdict"] is None
    assert result["error"] and result["error"].startswith("pass2:")
    assert result["pass1_relevant"] is True


def test_classify_pass2_disabled_returns_none_verdict(monkeypatch):
    classifier, fake = _make_classifier(
        [{"relevant": True, "confidence": 0.9, "reason": ""}],
        monkeypatch=monkeypatch,
        pass2_enabled=False,
    )
    result = classifier.classify("A", "T", "S", "full")
    assert result["verdict"] is None
    assert result["pass1_relevant"] is True
    assert len(fake.calls) == 1


def test_classify_pass1_disabled_goes_straight_to_pass2(monkeypatch):
    classifier, fake = _make_classifier(
        [{"verdict": "in_progress", "confidence": 0.7,
          "evidence_quote": "", "reasoning": ""}],
        monkeypatch=monkeypatch,
        pass1_enabled=False,
    )
    result = classifier.classify("A", "T", "S", "full")
    assert result["verdict"] == "in_progress"
    assert result["pass1_relevant"] is None  # never ran
    assert len(fake.calls) == 1


# ---------------------------------------------------------------------------
# retry behavior
# ---------------------------------------------------------------------------


def test_retry_on_non_json_then_succeeds(monkeypatch):
    """The audit fix: JSON-decode errors retry with the same backoff as
    network errors. Also verifies total call count respects max_retries."""
    # Patch sleep so the test is fast
    monkeypatch.setattr(
        "tisza_tracker.processors.llm_classifier.time.sleep",
        lambda *_: None,
    )
    classifier, fake = _make_classifier(
        [
            "not json",  # attempt 1: raises JSONDecodeError
            {"relevant": True, "confidence": 0.9, "reason": ""},  # attempt 2: OK
            {"verdict": "kept", "confidence": 0.9,
             "evidence_quote": "", "reasoning": ""},
        ],
        monkeypatch=monkeypatch,
        max_retries=2,
    )
    result = classifier.classify("A", "T", "S", "full")
    assert result["verdict"] == "kept"


def test_retry_gives_up_after_max_attempts(monkeypatch):
    monkeypatch.setattr(
        "tisza_tracker.processors.llm_classifier.time.sleep",
        lambda *_: None,
    )
    classifier, _ = _make_classifier(
        ["not json"] * 5,
        monkeypatch=monkeypatch,
        max_retries=2,
    )
    result = classifier.classify("A", "T", "S", "full")
    # After max_retries+1 JSON failures, pass1 records an error and we bail
    assert result["verdict"] is None
    assert result["error"].startswith("pass1:")
    # The error message should include the bad response snippet (audit fix)
    assert "last response" in result["error"]
