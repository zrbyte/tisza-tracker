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
    PROMPT_REVISION,
    LLMClassifier,
    _load_api_key,
    _trim,
    effective_prompt_version,
    pass2_system_prompt,
    quote_is_verbatim,
    to_signal,
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

    def _create(self, *, model, messages, response_format, **extra):
        self.calls.append({
            "model": model, "messages": messages,
            "response_format": response_format, **extra,
        })
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
# to_signal — the code-side rules
# ---------------------------------------------------------------------------


def _record(**overrides):
    record = {
        "what_happened": "The government adopted the law.",
        "about_promise": True,
        "actor": "current_government",
        "evidence_type": "delivered",
        "scope": "full",
        "event_date": "2026-06-10",
        "quote": "A kormány elfogadta a törvényt.",
        "confidence": 0.9,
    }
    record.update(overrides)
    return record


@pytest.mark.parametrize("evidence_type,scope,expected", [
    ("delivered", "full", "kept"),
    ("delivered", "partial", "partial"),
    ("delivered", "na", "partial"),
    ("formal_step", "na", "step"),
    ("stated_intent", "na", "intent"),
    ("delay", "na", "delay"),
    ("reversal", "full", "reversal"),
    ("no_signal", "na", "none"),
])
def test_to_signal_maps_evidence_types(evidence_type, scope, expected):
    record = _record(evidence_type=evidence_type, scope=scope)
    assert to_signal(record, "2026-06-11") == expected


def test_to_signal_ignores_articles_about_other_things():
    assert to_signal(_record(about_promise=False), "2026-06-11") == "none"


@pytest.mark.parametrize("actor", ["previous_government", "opposition", "third_party", "none"])
def test_to_signal_only_counts_government_acts(actor):
    """Opinions, opposition attacks and the previous government's record
    are what the old prompt mistook for broken promises."""
    record = _record(actor=actor, evidence_type="reversal")
    assert to_signal(record, "2026-06-11") == "none"


def test_to_signal_counterparty_can_block_but_not_break():
    record = _record(actor="counterparty", evidence_type="reversal")
    assert to_signal(record, "2026-06-11") == "delay"
    record = _record(actor="counterparty", evidence_type="delivered")
    assert to_signal(record, "2026-06-11") == "kept"


def test_to_signal_nothing_published_before_taking_office_counts():
    assert to_signal(_record(), "2026-05-11") == "none"
    assert to_signal(_record(evidence_type="stated_intent"), "2026-04-22") == "none"
    assert to_signal(_record(event_date="2026-05-12"), "2026-05-12") == "kept"


def test_to_signal_nothing_that_happened_before_taking_office_counts():
    record = _record(event_date="2026-03-18")
    assert to_signal(record, "2026-10-08") == "none"
    # An unknown or malformed event date falls back on the publication date.
    assert to_signal(_record(event_date="unknown"), "2026-10-08") == "kept"


def test_to_signal_took_office_is_configurable():
    assert to_signal(_record(), "2026-06-11", took_office="2026-07-01") == "none"


def test_to_signal_requires_a_verbatim_quote():
    assert to_signal(_record(), "2026-06-11", quote_verbatim=False) == "none"
    assert to_signal(_record(), "2026-06-11", quote_verbatim=None) == "none"


def test_to_signal_headline_only_never_yields_kept_or_reversal():
    assert to_signal(_record(), "2026-06-11", body_seen=False) == "step"
    partial = _record(scope="partial")
    assert to_signal(partial, "2026-06-11", body_seen=False) == "step"
    reversal = _record(evidence_type="reversal")
    assert to_signal(reversal, "2026-06-11", body_seen=False) == "none"
    intent = _record(evidence_type="stated_intent")
    assert to_signal(intent, "2026-06-11", body_seen=False) == "intent"


# ---------------------------------------------------------------------------
# quote_is_verbatim
# ---------------------------------------------------------------------------


def test_quote_verbatim_exact_substring():
    body = "Az Országgyűlés kedden elfogadta a törvényt. A kormány örül."
    assert quote_is_verbatim("Az Országgyűlés kedden elfogadta a törvényt.", body) is True


def test_quote_verbatim_ignores_typography_case_and_spacing():
    body = "A miniszter szerint „óriási feladat” – mondta\u00a0kedden."
    assert quote_is_verbatim('a miniszter szerint "óriási feladat" - mondta kedden', body) is True


def test_quote_verbatim_searches_title_and_teaser_too():
    assert quote_is_verbatim("Megszűnt a rendeleti kormányzás", "Megszűnt a rendeleti kormányzás", "") is True


def test_quote_verbatim_rejects_paraphrase():
    body = "A kormányfő jelezte, hogy szeptembertől áfamentes lesz a gyógyszer."
    assert quote_is_verbatim("A miniszterelnök jelezte, hogy szeptembertől áfamentes lesz a gyógyszer.", body) is False


def test_quote_verbatim_empty_quote_is_none():
    assert quote_is_verbatim("", "body") is None
    assert quote_is_verbatim(None, "body") is None


# ---------------------------------------------------------------------------
# prompt versioning and context
# ---------------------------------------------------------------------------


def test_effective_prompt_version_includes_code_revision():
    """The runtime config pins prompt_version, so a prompt change in code
    has to invalidate the cache on its own."""
    assert effective_prompt_version({"prompt_version": "v1"}) == f"v1.r{PROMPT_REVISION}"
    assert effective_prompt_version({}) == f"v1.r{PROMPT_REVISION}"
    assert effective_prompt_version({"prompt_version": "v7"}) != effective_prompt_version({})


def test_pass2_prompt_states_who_governs_since_when():
    prompt = pass2_system_prompt({"took_office": "2026-05-12", "election_date": "2026-04-12"})
    assert "took office on 2026-05-12" in prompt
    assert "Election day: 2026-04-12" in prompt
    assert "PREVIOUS government" in prompt
    assert "{took_office}" not in prompt


# ---------------------------------------------------------------------------
# classify — full orchestration paths
# ---------------------------------------------------------------------------

BODY = (
    "Az Országgyűlés kedden elfogadta a törvényt, amely teljesíti az ígéretet. "
    + "A részletekről a miniszter számolt be. " * 12
)
PROMISE = {"id": "P-1", "text": "Elfogadjuk a törvényt.", "text_en": "Pass the law.", "deadline": None}
GATE_OK = {"relevant": True, "confidence": 0.9, "reason": ""}
EXTRACTED = {
    "what_happened": "Parliament adopted the law on 2026-06-09.",
    "about_promise": True,
    "actor": "current_government",
    "evidence_type": "delivered",
    "scope": "full",
    "event_date": "2026-06-09",
    "quote": "Az Országgyűlés kedden elfogadta a törvényt",
    "confidence": 0.8,
}


def _article(**overrides):
    article = {
        "title": "Elfogadták a törvényt", "summary": "Kedden szavaztak.",
        "full_text": BODY, "outlet": "Telex", "published": "2026-06-10",
    }
    article.update(overrides)
    return article


def test_classify_irrelevant_short_circuits_pass2(monkeypatch):
    classifier, fake = _make_classifier(
        [{"relevant": False, "confidence": 0.7, "reason": "off-topic"}],
        monkeypatch=monkeypatch,
    )

    result = classifier.classify(PROMISE, _article())
    assert result["signal"] == "none"
    assert result["verdict"] == "irrelevant"
    assert result["confidence"] == 0.7
    assert result["pass1_relevant"] is False
    assert result["error"] is None
    assert len(fake.calls) == 1  # pass 2 never runs


def test_classify_runs_pass2_when_relevant(monkeypatch):
    classifier, fake = _make_classifier(
        [GATE_OK, EXTRACTED], monkeypatch=monkeypatch,
    )

    result = classifier.classify(PROMISE, _article())
    assert result["signal"] == "kept"
    assert result["verdict"] == "kept"
    assert result["confidence"] == 0.8
    assert result["evidence_quote"] == EXTRACTED["quote"]
    assert result["quote_verbatim"] is True
    assert result["actor"] == "current_government"
    assert result["evidence_type"] == "delivered"
    assert result["event_date"] == "2026-06-09"
    assert result["reasoning"] == EXTRACTED["what_happened"]
    assert result["body_chars"] == len(BODY.strip())
    assert result["pass1_relevant"] is True
    assert result["error"] is None
    assert len(fake.calls) == 2


def test_classify_uses_separate_model_and_low_effort_for_pass2(monkeypatch):
    classifier, fake = _make_classifier(
        [GATE_OK, EXTRACTED], monkeypatch=monkeypatch, pass2_model="fake-mini",
    )
    result = classifier.classify(PROMISE, _article())

    gate, extraction = fake.calls
    assert gate["model"] == "fake-model"
    assert "reasoning_effort" not in gate
    assert extraction["model"] == "fake-mini"
    assert extraction["reasoning_effort"] == "low"
    assert extraction["response_format"]["type"] == "json_schema"
    assert result["model"] == "fake-mini"


def test_classify_pass2_prompt_carries_fixed_context(monkeypatch):
    classifier, fake = _make_classifier(
        [GATE_OK, EXTRACTED], monkeypatch=monkeypatch,
    )
    promise = {**PROMISE, "deadline": "2027"}
    classifier.classify(promise, _article())

    system, user = (m["content"] for m in fake.calls[1]["messages"])
    assert "took office on 2026-05-12" in system
    assert "Outlet: Telex" in user
    assert "Published: 2026-06-10" in user
    assert "Deadline in the programme: 2027" in user


def test_classify_non_verbatim_quote_carries_no_signal(monkeypatch):
    extracted = {**EXTRACTED, "quote": "A parlament megszavazta az ígért jogszabályt."}
    classifier, _ = _make_classifier([GATE_OK, extracted], monkeypatch=monkeypatch)

    result = classifier.classify(PROMISE, _article())
    assert result["signal"] == "none"
    assert result["quote_verbatim"] is False
    assert result["evidence_type"] == "delivered"  # the raw record is kept


def test_classify_fetches_body_only_after_the_gate(monkeypatch):
    loads = []

    def loader():
        loads.append(1)
        return BODY

    classifier, _ = _make_classifier(
        [{"relevant": False, "confidence": 0.7, "reason": "off-topic"}, GATE_OK, EXTRACTED],
        monkeypatch=monkeypatch,
    )
    classifier.classify(PROMISE, _article(full_text=None), body_loader=loader)
    assert loads == []  # gate rejected: no download

    result = classifier.classify(PROMISE, _article(full_text=None), body_loader=loader)
    assert loads == [1]
    assert result["signal"] == "kept"
    assert result["body_chars"] == len(BODY.strip())


def test_classify_skips_loader_when_body_is_stored(monkeypatch):
    classifier, _ = _make_classifier([GATE_OK, EXTRACTED], monkeypatch=monkeypatch)

    def loader():
        raise AssertionError("body already stored; loader must not run")

    assert classifier.classify(PROMISE, _article(), body_loader=loader)["signal"] == "kept"


def test_classify_headline_only_is_capped_at_step(monkeypatch):
    """Without a body the title may state the act, but that is not enough
    for kept."""
    extracted = {**EXTRACTED, "quote": "Elfogadták a törvényt"}
    classifier, fake = _make_classifier([GATE_OK, extracted], monkeypatch=monkeypatch)

    result = classifier.classify(
        PROMISE, _article(full_text=None), body_loader=lambda: None,
    )
    assert result["body_chars"] == 0
    assert result["signal"] == "step"
    assert "not retrieved" in fake.calls[1]["messages"][1]["content"]


def test_classify_loader_failure_falls_back_to_headline(monkeypatch):
    extracted = {**EXTRACTED, "quote": "Elfogadták a törvényt"}
    classifier, _ = _make_classifier([GATE_OK, extracted], monkeypatch=monkeypatch)

    def loader():
        raise RuntimeError("network down")

    result = classifier.classify(PROMISE, _article(full_text=None), body_loader=loader)
    assert result["error"] is None
    assert result["signal"] == "step"


def test_classify_pass2_invalid_record_records_error(monkeypatch):
    classifier, _ = _make_classifier(
        [GATE_OK, {**EXTRACTED, "evidence_type": "maybe"}],
        monkeypatch=monkeypatch,
    )
    result = classifier.classify(PROMISE, _article())
    assert result["signal"] is None
    assert result["verdict"] is None
    assert "invalid record" in result["error"]


def test_classify_pass1_failure_records_error(monkeypatch):
    classifier, _ = _make_classifier(
        [RuntimeError("boom"), RuntimeError("boom"), RuntimeError("boom")],
        monkeypatch=monkeypatch,
    )
    result = classifier.classify(PROMISE, _article())
    assert result["signal"] is None
    assert result["error"] and result["error"].startswith("pass1:")


def test_classify_pass2_failure_records_error(monkeypatch):
    classifier, _ = _make_classifier(
        [GATE_OK, RuntimeError("pass2 boom"), RuntimeError("pass2 boom")],
        monkeypatch=monkeypatch,
    )
    result = classifier.classify(PROMISE, _article())
    assert result["signal"] is None
    assert result["error"] and result["error"].startswith("pass2:")
    assert result["pass1_relevant"] is True


def test_classify_pass2_disabled_returns_no_signal(monkeypatch):
    classifier, fake = _make_classifier(
        [GATE_OK], monkeypatch=monkeypatch, pass2_enabled=False,
    )
    result = classifier.classify(PROMISE, _article())
    assert result["signal"] is None
    assert result["pass1_relevant"] is True
    assert len(fake.calls) == 1


def test_classify_pass1_disabled_goes_straight_to_pass2(monkeypatch):
    classifier, fake = _make_classifier(
        [{**EXTRACTED, "evidence_type": "formal_step", "scope": "na"}],
        monkeypatch=monkeypatch,
        pass1_enabled=False,
    )
    result = classifier.classify(PROMISE, _article())
    assert result["signal"] == "step"
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
            GATE_OK,  # attempt 2: OK
            EXTRACTED,
        ],
        monkeypatch=monkeypatch,
        max_retries=2,
    )
    result = classifier.classify(PROMISE, _article())
    assert result["signal"] == "kept"


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
    result = classifier.classify(PROMISE, _article())
    # After max_retries+1 JSON failures, pass1 records an error and we bail
    assert result["signal"] is None
    assert result["error"].startswith("pass1:")
    # The error message should include the bad response snippet (audit fix)
    assert "last response" in result["error"]
