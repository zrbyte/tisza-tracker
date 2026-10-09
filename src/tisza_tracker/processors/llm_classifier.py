"""LLM-based promise evidence classifier.

Two-pass cascade using an OpenAI-compatible chat-completions endpoint:

1. **Pass 1 — relevance gate** (cheap):  only title + summary are sent.
   Returns ``{relevant: bool, confidence: float, reason: str}``.  An article
   that fails this gate is recorded with signal ``none`` without further work.

2. **Pass 2 — evidence extraction**:  uses the full article body.  The model
   does not pick a verdict.  It reports who acted and what kind of act the
   article describes (``actor``, ``evidence_type``, ``scope``, ``event_date``,
   ``quote``), and :func:`to_signal` turns that record into a status signal in
   code.  Tone, third-party opinion and the previous government's record are
   therefore separate, checkable fields instead of one holistic guess.

Both passes request JSON output.  Failures are recorded as rows with an
``error`` message; ``tt classify`` retries them on later runs.
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ..core.promise_store import SIGNAL_TO_VERDICT

logger = logging.getLogger(__name__)

ACTORS = (
    "current_government", "counterparty", "previous_government",
    "opposition", "third_party", "none",
)
EVIDENCE_TYPES = (
    "delivered", "formal_step", "stated_intent", "delay", "reversal", "no_signal",
)
SCOPES = ("full", "partial", "na")

# Bumped whenever the pass-2 prompt, schema or signal mapping changes.  It is
# part of the stored ``prompt_version``, so a code change invalidates cached
# extractions without anyone having to edit the runtime config.
PROMPT_REVISION = "2"

DEFAULT_GOVERNMENT = {"election_date": "2026-04-12", "took_office": "2026-05-12"}
DEFAULT_MIN_BODY_CHARS = 300

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

_PASS2_SYSTEM = """You extract evidence about ONE campaign promise of the Hungarian government from ONE news article.
You do not judge whether the policy is good and you do not report the article's tone. You report what was DONE, and by WHOM.

POLITICAL CONTEXT (fixed facts)
- The promise comes from the 2026 election programme of the Tisza party (leader: Magyar Péter).
- Election day: {election_date}. The Tisza government took office on {took_office}; since then it is the CURRENT government ("Tisza-kormány", "Magyar-kormány", "az új kormány", "a kabinet").
- The PREVIOUS government was the Fidesz–KDNP government of Orbán Viktor (2010–2026). Whatever it or its ministers decided, signed, promised, failed to do or left behind belongs to the previous government, even when the article was published after the change of government. Fidesz and KDNP are now OPPOSITION parties.
- Nothing that happened before {took_office} can be a delivered outcome, formal step, delay or reversal by the current government; before that date its politicians could only state intentions.

HOW TO WORK
1. Re-read the promise literally: what concrete outcome was promised, and by when?
2. Find the single most important NEW thing the article reports as FACT about that outcome.
3. Decide who did it (actor) and what kind of evidence it is (evidence_type).
Ask yourself: "After the event reported here, is the promised outcome closer, further away, or unchanged, and whose doing is it?"

actor
- current_government: the Tisza government (PM, ministers, state secretaries, spokespeople, ministries) or the governing majority in Parliament (bills it submits, laws it passes).
- counterparty: a body whose official decision directly delivers or blocks the promised outcome (European Commission or Council, a court, the President of the Republic, a foreign government).
- previous_government: the Orbán government and its officials.
- opposition: opposition parties and politicians.
- third_party: experts, analysts, lobby groups, chambers, unions, professional bodies, companies, rectors, mayors, NGOs, readers or commenters, and the journalist's own opinion.
- none: no actor relevant to this promise.

evidence_type
- delivered: the PROMISED outcome itself (not just any government measure) now exists or is in force: law adopted in the final vote or promulgated; decree in force; body legally created or abolished, or already operating; membership completed; money actually paid. Something only announced for a future date is not delivered. Set scope to "partial" when only part of the promise is delivered, or it is delivered in a narrower or altered form.
- formal_step: a concrete official act on the way, short of delivery (cabinet decision; draft law published for consultation or submitted to Parliament; agreement signed; budget allocated; commissioner appointed; tender launched).
- stated_intent: officials announce, repeat or detail the plan or its timetable without a new official act.
- delay: officials postpone it, or a publicly stated deadline has demonstrably passed without delivery.
- reversal: the current government officially abandons or refuses the promise, or adopts a measure that does the opposite. This needs a decision or on-the-record statement BY THE CURRENT GOVERNMENT, reported as fact.
- no_signal: none of the above.

ALWAYS no_signal:
- acts, contracts, promises, failures or legacy of the previous government;
- accusations, predictions or attacks by opposition politicians;
- opinions, demands, forecasts, warnings or preferences of third parties, and reader comments;
- what the government "should", "must", "may", "could" or "is thinking of" doing, and what others expect it to do;
- the promise itself being recalled, quoted or summarised without a new government act or statement;
- isolated incidents, accidents, statistics or the general state of affairs;
- background paragraphs and history;
- articles that are really about a different promise, or only mention this topic in passing.

RULES
R1 Criticism is not reversal. If someone attacks a government plan, the plan exists: classify the underlying government act (usually formal_step or stated_intent with actor current_government), not the criticism. If no government act is reported at all, answer no_signal.
R2 A promise delivered in a modified, more expensive or narrower form is "delivered" with scope "partial", not "reversal".
R3 Check the direction before you choose. A law, decree or decision of the government can run AGAINST the promise (for example the promise was not to raise something and the measure raises it; or to keep something and the measure closes it): that is "reversal", never "delivered" or "formal_step". Conversely an act that implements the promise is never a reversal, however controversial its details.
R4 A claim is not a fact because an outlet prints it in a headline. Prefer what the body reports as having happened, and attribute claims to whoever makes them.
R5 If you were given only a headline and a one-line teaser that do not themselves state the act, answer no_signal rather than guess.
R6 Do not infer intentions or acts that the article does not report.
R7 quote must be copied verbatim from the article and must be the sentence that reports the act you chose (empty string for no_signal).

Return JSON only."""

_PASS2_SCHEMA = {
    "name": "promise_evidence",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["what_happened", "about_promise", "actor", "evidence_type", "scope",
                     "event_date", "quote", "confidence"],
        "properties": {
            "what_happened": {"type": "string", "description": "One English sentence: who did what, when."},
            "about_promise": {"type": "boolean"},
            "actor": {"type": "string", "enum": list(ACTORS)},
            "evidence_type": {"type": "string", "enum": list(EVIDENCE_TYPES)},
            "scope": {"type": "string", "enum": list(SCOPES)},
            "event_date": {"type": "string", "description": "YYYY-MM-DD or 'unknown'"},
            "quote": {"type": "string"},
            "confidence": {"type": "number"},
        },
    },
}

_BODY_LIMIT = 8000


def _trim(text: str, limit: int) -> str:
    if text is None:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def effective_prompt_version(llm_cfg: Dict[str, Any]) -> str:
    """Cache key for classifications: the config knob plus the code revision."""
    return f"{llm_cfg.get('prompt_version') or 'v1'}.r{PROMPT_REVISION}"


def government_context(government: Optional[Dict[str, Any]]) -> Dict[str, str]:
    ctx = dict(DEFAULT_GOVERNMENT)
    for key, value in (government or {}).items():
        if key in ctx and value:
            ctx[key] = str(value)[:10]
    return ctx


def pass2_system_prompt(government: Optional[Dict[str, Any]] = None) -> str:
    return _PASS2_SYSTEM.format(**government_context(government))


def pass2_user_prompt(promise: Dict[str, Any], article: Dict[str, Any], body: str) -> str:
    body = _trim(body or "", _BODY_LIMIT)
    return (
        f"PROMISE {promise['id']} (Hungarian): {promise['text']}\n"
        f"English gloss: {promise.get('text_en') or '-'}\n"
        f"Deadline in the programme: {promise.get('deadline') or 'none stated'}\n\n"
        f"ARTICLE\nOutlet: {article.get('outlet') or '-'}\n"
        f"Published: {article.get('published') or '-'}\n"
        f"Title: {article.get('title') or ''}\nTeaser: {article.get('summary') or '-'}\n"
        + (f"Body:\n{body}\n" if body
           else "Body: (not retrieved; only the title and teaser are available)\n")
    )


_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def to_signal(
    record: Dict[str, Any],
    published: Optional[str],
    *,
    took_office: str = DEFAULT_GOVERNMENT["took_office"],
    body_seen: bool = True,
    quote_verbatim: Optional[bool] = True,
) -> str:
    """Deterministic mapping from an extracted record to a status signal.

    Rules enforced here rather than left to the model:

    * only acts of the current government (or of a counterparty whose decision
      delivers or blocks the outcome) count;
    * nothing dated before the government took office counts;
    * the quote must be found verbatim in the article;
    * headline-only evidence never yields ``kept``, ``partial`` or
      ``reversal``.
    """
    if not record.get("about_promise") or record.get("evidence_type") == "no_signal":
        return "none"
    actor, evidence = record.get("actor"), record.get("evidence_type")
    if actor not in ("current_government", "counterparty"):
        return "none"

    event = str(record.get("event_date") or "")
    if (published and str(published)[:10] < took_office) or (
        _ISO_DATE.match(event) and event < took_office
    ):
        return "none"
    if not quote_verbatim:
        return "none"

    if evidence == "delivered":
        signal = "kept" if record.get("scope") == "full" else "partial"
    elif evidence == "reversal":
        # A counterparty can block a promise but cannot break it.
        signal = "reversal" if actor == "current_government" else "delay"
    else:
        signal = {"formal_step": "step", "stated_intent": "intent", "delay": "delay"}.get(
            evidence, "none"
        )

    if not body_seen:
        if signal in ("kept", "partial"):
            return "step"
        if signal == "reversal":
            return "none"
    return signal


_WS = re.compile(r"\s+")
_QUOTE_MARKS = re.compile("[„“”«»\"'’‘`]")
_DASHES = re.compile("[‐‑‒–—−-]")


def _normalize_for_quote(text: str) -> str:
    text = unicodedata.normalize("NFKC", html.unescape(text or ""))
    text = _QUOTE_MARKS.sub('"', text)
    text = _DASHES.sub("-", text).replace("…", "...")
    return _WS.sub(" ", text).strip().casefold()


def quote_is_verbatim(quote: Optional[str], *texts: Optional[str]) -> Optional[bool]:
    """Whether *quote* occurs in *texts*, ignoring typography, case and spacing.

    Returns None for an empty quote.
    """
    needle = _normalize_for_quote(quote or "").strip(" \"'.,;:!?-")
    if not needle:
        return None
    return needle in _normalize_for_quote(" ".join(t or "" for t in texts))


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


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class LLMClassifier:
    """Two-pass OpenAI-compatible classifier."""

    def __init__(
        self,
        llm_cfg: Dict[str, Any],
        secrets_dir: Optional[Path] = None,
        government: Optional[Dict[str, Any]] = None,
    ) -> None:
        from openai import OpenAI  # local import; dep is optional for non-classify flows

        self.model = llm_cfg.get("model") or "gpt-5-nano"
        self.pass2_model = llm_cfg.get("pass2_model") or "gpt-5-mini"
        # Without a low effort setting the small reasoning models take 30 s+
        # per article; set the key to null in config to omit the parameter.
        self.pass2_reasoning_effort = llm_cfg.get("pass2_reasoning_effort", "low")
        self.prompt_version = effective_prompt_version(llm_cfg)
        self.timeout = float(llm_cfg.get("request_timeout") or 30)
        self.max_retries = int(llm_cfg.get("max_retries") or 2)
        self.pass1_enabled = bool(llm_cfg.get("pass1_enabled", True))
        self.pass2_enabled = bool(llm_cfg.get("pass2_enabled", True))
        self.min_body_chars = int(llm_cfg.get("min_body_chars") or DEFAULT_MIN_BODY_CHARS)
        self.government = government_context(government)

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

    def _chat_json(
        self,
        system: str,
        user: str,
        *,
        model: Optional[str] = None,
        schema: Optional[Dict[str, Any]] = None,
        reasoning_effort: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Single JSON-mode chat call with retry on transient errors.

        Retries both network/API errors and JSON-decode errors, with linear
        backoff; the OpenAI SDK's own retry is disabled (see ``__init__``) to
        avoid double-retry stacking.  The last bad-response snippet is kept
        on the exception message for easier debugging.
        """
        request: Dict[str, Any] = {
            "model": model or self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": (
                {"type": "json_schema", "json_schema": schema}
                if schema else {"type": "json_object"}
            ),
        }
        if reasoning_effort:
            request["reasoning_effort"] = reasoning_effort

        last_exc: Optional[Exception] = None
        last_content: Optional[str] = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._client.chat.completions.create(**request)
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

    def extract(
        self,
        promise: Dict[str, Any],
        article: Dict[str, Any],
        body: str = "",
    ) -> Dict[str, Any]:
        """Pass 2: ask the model who did what.  Returns its raw record."""
        return self._chat_json(
            pass2_system_prompt(self.government),
            pass2_user_prompt(promise, article, body),
            model=self.pass2_model,
            schema=_PASS2_SCHEMA,
            reasoning_effort=self.pass2_reasoning_effort,
        )

    def signal_for(
        self,
        record: Dict[str, Any],
        article: Dict[str, Any],
        body: str,
    ) -> Dict[str, Any]:
        """Apply the code-side rules to a pass-2 record."""
        # The model saw the title, the teaser and the first _BODY_LIMIT
        # characters of the body, so that is where the quote has to be.
        verbatim = quote_is_verbatim(
            record.get("quote"), article.get("title"), article.get("summary"),
            _trim(body or "", _BODY_LIMIT),
        )
        signal = to_signal(
            record,
            article.get("published"),
            took_office=self.government["took_office"],
            body_seen=len(body or "") >= self.min_body_chars,
            quote_verbatim=verbatim,
        )
        return {"signal": signal, "quote_verbatim": verbatim}

    # ---- orchestration ----

    def classify(
        self,
        promise: Dict[str, Any],
        article: Dict[str, Any],
        body_loader: Optional[Callable[[], Optional[str]]] = None,
    ) -> Dict[str, Any]:
        """Run the two-pass cascade and return a normalized result dict.

        *article* carries ``title``, ``summary``, ``full_text``, ``outlet`` and
        ``published``.  *body_loader* is called to fetch the body when the
        article passes the gate without one, so only relevant articles cost a
        download.
        """
        result: Dict[str, Any] = {
            "signal": None,
            "verdict": None,
            "confidence": None,
            "evidence_quote": None,
            "quote_verbatim": None,
            "reasoning": None,
            "actor": None,
            "evidence_type": None,
            "scope": None,
            "event_date": None,
            "body_chars": None,
            "pass1_relevant": None,
            "pass1_confidence": None,
            "error": None,
            "model": self.model,
            "prompt_version": self.prompt_version,
        }
        title = article.get("title") or ""
        summary = article.get("summary") or ""

        # Pass 1: gate
        if self.pass1_enabled:
            try:
                p1 = self.relevance_gate(promise["text"], title, summary)
            except Exception as exc:
                result["error"] = f"pass1: {exc}"
                logger.warning("Pass 1 failed: %s", exc)
                return result

            relevant = bool(p1.get("relevant"))
            result["pass1_relevant"] = relevant
            result["pass1_confidence"] = _as_float(p1.get("confidence", 0.0))

            if not relevant:
                result["signal"] = "none"
                result["verdict"] = SIGNAL_TO_VERDICT["none"]
                result["confidence"] = result["pass1_confidence"]
                result["reasoning"] = p1.get("reason")
                return result

        if not self.pass2_enabled:
            return result

        body = (article.get("full_text") or "").strip()
        if not body and body_loader is not None:
            try:
                body = (body_loader() or "").strip()
            except Exception as exc:
                logger.warning("Could not load article body: %s", exc)
        result["body_chars"] = len(body)

        # Pass 2: evidence extraction
        result["model"] = self.pass2_model
        try:
            p2 = self.extract(promise, article, body)
        except Exception as exc:
            result["error"] = f"pass2: {exc}"
            logger.warning("Pass 2 failed: %s", exc)
            return result

        if p2.get("actor") not in ACTORS or p2.get("evidence_type") not in EVIDENCE_TYPES:
            result["error"] = (
                f"pass2: invalid record (actor={p2.get('actor')!r}, "
                f"evidence_type={p2.get('evidence_type')!r})"
            )
            return result

        result.update(self.signal_for(p2, article, body))
        result["verdict"] = SIGNAL_TO_VERDICT[result["signal"]]
        result["confidence"] = _as_float(p2.get("confidence", 0.0))
        result["evidence_quote"] = p2.get("quote") or None
        result["reasoning"] = p2.get("what_happened") or None
        result["actor"] = p2.get("actor")
        result["evidence_type"] = p2.get("evidence_type")
        result["scope"] = p2.get("scope") if p2.get("scope") in SCOPES else "na"
        result["event_date"] = p2.get("event_date") or None
        return result
