"""Explanations for findings (HLD 9.3): pacing, retries, cache, grounding check, templates.

The explainer only adds ``Finding.explanation`` and the executive summary. Status, severity,
reason, expected and found come from the policy engine and are never changed here (HLD 0.3).
Every LLM answer is checked before use:

* ``quoted_evidence`` must be an exact substring of the clause text after whitespace
  normalisation ("" for MISSING);
* every number in the answer must appear in the prompt's inputs (D37), so a made-up
  "45 days" cannot reach the reviewer.

A failed check is retried once with a correction note; after that the template explanation is used.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
import threading
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from contractguard.config import Settings, get_settings, get_templates
from contractguard.llm.base import LLMError, LLMProvider
from contractguard.llm.prompts import (
    EXPLAIN_FIELDS,
    EXPLAIN_SCHEMA,
    EXPLAIN_SYSTEM,
    EXPLAIN_USER,
    GROUNDING_RETRY_NOTE,
    MISSING_CLAUSE_TEXT,
    PROMPT_VERSION,
    SUMMARY_SCHEMA,
    SUMMARY_SYSTEM,
    SUMMARY_USER,
)
from contractguard.models import Clause, ContractMeta, Explanation, Finding
from contractguard.policy.schema import Rule

log = logging.getLogger(__name__)

EXPLAINED_STATUSES = frozenset({"NON_COMPLIANT", "MISSING", "NEEDS_REVIEW"})
MAX_CLAUSE_CHARS = 2500
_SEVERITY_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, None: 3}
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def normalize_ws(text: str) -> str:
    return " ".join(text.split())


def is_grounded(quote: str, clause_text: str, status: str) -> bool:
    if status == "MISSING":
        return quote == ""
    quote = normalize_ws(quote)
    return bool(quote) and quote in normalize_ws(clause_text)


def unsupported_numbers(answer: dict[str, Any], source: str) -> list[str]:
    """Numbers in the answer's prose fields that do not occur anywhere in ``source``.

    ``quoted_evidence`` is skipped: the grounding check already ties it to the clause.
    """
    known = {n.replace(",", "") for n in _NUMBER.findall(source)}
    text = " ".join(str(v) for k, v in answer.items() if k != "quoted_evidence")
    return sorted({n for n in _NUMBER.findall(text) if n.replace(",", "") not in known})


# ----- pacing ---------------------------------------------------------------------------------
class RateLimiter:
    """Token bucket: at most ``rpm`` calls per minute, bursts up to ``rpm``."""

    def __init__(
        self,
        rpm: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.capacity = max(1, rpm)
        self.rate = self.capacity / 60.0
        self.tokens = float(self.capacity)
        self.clock, self.sleep = clock, sleep
        self.updated = clock()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = self.clock()
            self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
            self.updated = now
            if self.tokens < 1:
                wait = (1 - self.tokens) / self.rate
                self.sleep(wait)
                self.updated = self.clock()
                self.tokens = 1.0
            self.tokens -= 1


# ----- cache ----------------------------------------------------------------------------------
class LLMCache:
    """The ``llm_cache`` SQLite table (HLD 10.3), via the standard library ``sqlite3``.

    ``path=None`` keeps the cache in memory (tests, CLI runs without a database).
    """

    def __init__(self, path: str | Path | None = None) -> None:
        if path is not None:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path) if path else ":memory:", check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._conn:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS llm_cache (key TEXT PRIMARY KEY, "
                "response_json TEXT NOT NULL, model TEXT, created_at TEXT NOT NULL)"
            )

    @staticmethod
    def make_key(*parts: str | None) -> str:
        return hashlib.sha256("\x1f".join(p or "" for p in parts).encode()).hexdigest()

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT response_json FROM llm_cache WHERE key = ?", (key,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def set(self, key: str, value: dict[str, Any], model: str | None) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO llm_cache VALUES (?, ?, ?, ?)",
                (key, json.dumps(value), model, datetime.now(UTC).isoformat()),
            )


# ----- explainer ------------------------------------------------------------------------------
class Explainer:
    def __init__(
        self,
        provider: LLMProvider | None,
        cache: LLMCache | None = None,
        settings: Settings | None = None,
        limiter: RateLimiter | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings or get_settings()
        self.provider = provider
        self.cache = cache if cache is not None else LLMCache()
        self.limiter = limiter or RateLimiter(self.settings.llm.rpm)
        self.sleep = sleep
        self.t = get_templates()
        self.stats = {"llm": 0, "template": 0, "cache_hits": 0, "grounding_failures": 0,
                      "number_failures": 0, "errors": 0}  # fmt: skip

    # ----- templates -------------------------------------------------------------------------
    def template_explanation(self, finding: Finding, rule: Rule | None) -> Explanation:
        cfg = self.t["explanation"]
        status_label = cfg["status_labels"].get(finding.status, finding.status)
        policy_text = rule.policy_text if rule else finding.reason
        action = rule.recommendation_template if rule else "Review the clause manually."
        quote = "" if finding.status == "MISSING" else (finding.evidence_text or "")
        explanation = finding.reason
        if finding.status == "MISSING":
            explanation = f"{finding.reason} {cfg['missing_evidence_note']}"
        return Explanation(
            summary=cfg["summary"].format(rule_name=finding.rule_name, status_label=status_label),
            explanation=explanation,
            why_it_matters=cfg["why_it_matters"].format(policy_text=policy_text),
            suggested_review_action=action,
            quoted_evidence=quote,
            source="template",
            model=None,
            prompt_version=PROMPT_VERSION,
        )

    # ----- one finding -----------------------------------------------------------------------
    def _call(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        """One provider call with pacing and exponential backoff on retryable errors."""
        assert self.provider is not None
        tries = max(1, self.settings.llm.max_retries)
        for attempt in range(tries):
            self.limiter.acquire()
            try:
                return self.provider.generate_json(
                    system, user, schema,
                    temperature=self.settings.llm.temperature,
                    timeout_s=self.settings.llm.timeout_s,
                )  # fmt: skip
            except LLMError as exc:
                if not exc.retryable or attempt == tries - 1:
                    raise
                delay = 2.0 * 2**attempt  # 2 s, 4 s, 8 s
                log.info("LLM call failed (%s); retrying in %.0f s", exc, delay)
                self.sleep(delay)
        raise LLMError("unreachable")  # pragma: no cover

    def explain(
        self,
        finding: Finding,
        rule: Rule | None,
        clause_text: str,
        contract_type: str,
        our_alias: str,
        counterparty_alias: str,
    ) -> Explanation:
        if self.provider is None or rule is None:
            self.stats["template"] += 1
            return self.template_explanation(finding, rule)

        clause_text = clause_text[:MAX_CLAUSE_CHARS]
        prompt_clause = clause_text if finding.status != "MISSING" else MISSING_CLAUSE_TEXT
        user = EXPLAIN_USER.format(
            contract_type=contract_type,
            our_alias=our_alias,
            counterparty_alias=counterparty_alias,
            rule_name=rule.name,
            policy_text=rule.policy_text,
            status=finding.status,
            severity=finding.severity or "NONE",
            expected=finding.expected or "-",
            found=finding.found or "-",
            location=finding.location or "-",
            clause_text=prompt_clause,
        )
        key = LLMCache.make_key(PROMPT_VERSION, finding.rule_id, finding.status, clause_text,
                                finding.expected, finding.found, self.provider.model)  # fmt: skip
        cached = self.cache.get(key)
        if cached is not None:
            self.stats["cache_hits"] += 1
            self.stats["llm"] += 1
            return Explanation(**cached)

        answer: dict[str, Any] | None = None
        for attempt in range(2):  # first try + one grounding retry
            try:
                raw = self._call(EXPLAIN_SYSTEM, user + (GROUNDING_RETRY_NOTE if attempt else ""),
                                 EXPLAIN_SCHEMA)  # fmt: skip
            except LLMError as exc:
                log.warning("LLM explanation failed for %s: %s", finding.rule_id, exc)
                self.stats["errors"] += 1
                break
            if not all(isinstance(raw.get(k), str) for k in EXPLAIN_FIELDS):
                self.stats["errors"] += 1
                continue
            if not is_grounded(raw["quoted_evidence"], clause_text, finding.status):
                self.stats["grounding_failures"] += 1
                continue
            if unsupported_numbers(raw, user):
                self.stats["number_failures"] += 1
                continue
            answer = raw
            break

        if answer is None:
            self.stats["template"] += 1
            return self.template_explanation(finding, rule)
        explanation = Explanation(
            **{k: answer[k].strip() for k in EXPLAIN_FIELDS},
            source="llm",
            model=self.provider.model,
            prompt_version=PROMPT_VERSION,
        )
        self.cache.set(key, explanation.model_dump(), self.provider.model)
        self.stats["llm"] += 1
        return explanation

    # ----- whole report ----------------------------------------------------------------------
    def explain_findings(
        self,
        findings: Sequence[Finding],
        rules: Sequence[Rule],
        clauses: Sequence[Clause],
        meta: ContractMeta,
    ) -> list[Finding]:
        """Explain NON_COMPLIANT / MISSING / NEEDS_REVIEW findings; the top ``max_findings`` by
        severity go to the LLM, the rest get templates. Other findings stay unexplained."""
        by_rule = {r.id: r for r in rules}
        by_clause = {c.clause_id: c for c in clauses}
        our = next((p.alias or p.name for p in meta.parties if p.role == "OUR_ORG"), "unknown")
        other = next((p.alias or p.name for p in meta.parties if p.role == "COUNTERPARTY"),
                     "unknown")  # fmt: skip

        flagged = [i for i, f in enumerate(findings) if f.status in EXPLAINED_STATUSES]
        ranked = sorted(flagged, key=lambda i: (_SEVERITY_RANK[findings[i].severity], i))
        to_llm = set(ranked[: self.settings.llm.max_findings])

        out = list(findings)
        for i in flagged:
            f = findings[i]
            rule = by_rule.get(f.rule_id)
            if i not in to_llm:
                self.stats["template"] += 1
                explanation = self.template_explanation(f, rule)
            else:
                text = "\n\n".join(by_clause[c].text for c in f.clause_ids if c in by_clause)
                explanation = self.explain(f, rule, text, meta.contract_type, our, other)
            out[i] = f.model_copy(update={"explanation": explanation})
        return out

    def executive_summary(self, findings: Sequence[Finding], contract_type: str) -> str:
        flagged = [f for f in findings if f.status in EXPLAINED_STATUSES]
        if self.provider is not None and flagged:
            lines = "\n".join(
                f"- {f.status}, {f.severity}: "
                f"{f.explanation.summary if f.explanation else f.reason}"
                for f in flagged
            )
            counts = ", ".join(
                f"{s}={sum(f.status == s for f in findings)}" for s in sorted(EXPLAINED_STATUSES)
            )
            user = SUMMARY_USER.format(contract_type=contract_type, counts=counts, findings=lines)
            try:
                raw = self._call(SUMMARY_SYSTEM, user, SUMMARY_SCHEMA)
                text = raw.get("executive_summary")
                if isinstance(text, str) and text.strip():
                    if not unsupported_numbers({"summary": text}, user):
                        return text.strip()
                    self.stats["number_failures"] += 1
            except LLMError as exc:
                log.warning("LLM executive summary failed: %s", exc)
        return self.template_summary(findings)

    def template_summary(self, findings: Sequence[Finding]) -> str:
        cfg = self.t["executive_summary"]
        applicable = [f for f in findings if f.status != "NOT_APPLICABLE"]
        count = {s: sum(f.status == s for f in applicable) for s in
                 ("NON_COMPLIANT", "MISSING", "NEEDS_REVIEW", "COMPLIANT")}  # fmt: skip
        text = cfg["counts"].format(
            n_rules=len(applicable),
            n_noncompliant=count["NON_COMPLIANT"],
            n_missing=count["MISSING"],
            n_review=count["NEEDS_REVIEW"],
            n_compliant=count["COMPLIANT"],
        )
        issues = [f for f in findings if f.status in ("NON_COMPLIANT", "MISSING")][:3]
        if issues:
            listed = "; ".join(f"{f.rule_name} ({f.severity}, {f.reason})" for f in issues)
            return f"{text} {cfg['top_issues'].format(issues=listed)}"
        return f"{text} {cfg['no_issues']}"


def make_provider(settings: Settings | None = None) -> LLMProvider | None:
    """The configured provider, or None when the LLM is off or not configured (templates only)."""
    settings = settings or get_settings()
    llm = settings.llm
    if llm.provider == "none":
        return None
    if llm.provider == "mock":
        from contractguard.llm.mock import MockProvider

        return MockProvider()
    if not llm.model:
        log.warning("LLM_MODEL is not set: using template explanations")
        return None
    if llm.provider == "gemini":
        if settings.gemini_api_key is None:
            log.warning("GEMINI_API_KEY is not set: using template explanations")
            return None
        from contractguard.llm.gemini import GeminiProvider

        return GeminiProvider(settings.gemini_api_key.get_secret_value(), llm.model)
    from contractguard.llm.ollama import OllamaProvider

    return OllamaProvider(llm.model, llm.ollama_host)
