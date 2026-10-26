"""Deterministic policy evaluation (HLD 3.3, 8.3).

For each rule the engine decides status and severity from the classified clauses and extracted
facts only. The LLM is never consulted here (HLD 0.3). Text fields come from
``config/templates.yaml``. Without an embedder, step 3's semantic search is skipped: an empty
category then goes straight to MISSING / NOT_APPLICABLE, and the caller adds a warning.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from contractguard.config import Settings, get_settings, get_templates
from contractguard.embeddings.service import Embedder, cosine_top_k
from contractguard.models import Clause, Fact, Finding, Severity, Status
from contractguard.policy.schema import Policy, Rule

log = logging.getLogger(__name__)

RULE_KINDS = frozenset({"BODY", "EXHIBIT"})
STATUS_ORDER: dict[str, int] = {
    "NON_COMPLIANT": 0,
    "MISSING": 1,
    "NEEDS_REVIEW": 2,
    "COMPLIANT": 3,
    "NOT_APPLICABLE": 4,
}
SEVERITY_ORDER: dict[str | None, int] = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, None: 3}


def _fmt_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def location(clauses: Sequence[Clause]) -> str | None:
    """``Page N`` / ``Pages N-M`` for PDF clauses, ``Section X`` / ``Sections X, Y`` for DOCX."""
    if not clauses:
        return None
    starts = [c.page_start for c in clauses if c.page_start is not None]
    ends = [c.page_end or c.page_start for c in clauses if c.page_start is not None]
    if starts:
        first, last = min(starts), max(e for e in ends if e is not None)
        return f"Page {first}" if first == last else f"Pages {first}-{last}"
    refs = list(dict.fromkeys(c.number or c.section_path for c in clauses))
    return ("Section " if len(refs) == 1 else "Sections ") + ", ".join(refs)


@dataclass
class _ClauseIndex:
    """BODY clauses and their embeddings, encoded once per contract on first use."""

    clauses: list[Clause]
    embedder: Embedder | None
    _matrix: np.ndarray | None = None

    def best(self, text: str) -> tuple[Clause, float] | None:
        if self.embedder is None or not self.clauses:
            return None
        if self._matrix is None:
            self._matrix = self.embedder.encode([c.text for c in self.clauses])
        query = self.embedder.encode([text])[0]
        top = cosine_top_k(query, self._matrix, k=1)
        return (self.clauses[top[0][0]], top[0][1]) if top else None


class PolicyEngine:
    def __init__(
        self,
        policy: Policy,
        embedder: Embedder | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.policy = policy
        self.embedder = embedder
        settings = settings or get_settings()
        self.tau_missing = (
            policy.thresholds.tau_missing
            if policy.thresholds.tau_missing is not None
            else settings.policy.tau_missing
        )
        self.t: dict[str, Any] = get_templates()

    # ----- text helpers -------------------------------------------------------------------
    def _cat(self, category: str) -> str:
        return str(self.t["category_labels"].get(category, category.title()))

    def _fact_cfg(self, key: str | None) -> dict[str, Any]:
        return dict(self.t["facts"].get(key or "", {"label": key or ""}))

    def _value_text(self, rule: Rule, value: object) -> str:
        cfg = self._fact_cfg(rule.fact)
        if isinstance(value, bool):
            return str(cfg.get(str(value).lower(), value))
        if isinstance(value, int | float):
            unit = cfg.get("unit")
            return f"{_fmt_number(value)} {unit}" if unit else _fmt_number(value)
        return str(value)

    def _expected(self, rule: Rule) -> str:
        exp = self.t["expected"]
        if rule.check == "BOOLEAN_EQUALS":
            return self._value_text(rule, rule.expected)
        if rule.check in ("NUMERIC_MIN", "NUMERIC_MAX"):
            unit = self._fact_cfg(rule.fact).get("unit", "")
            return str(
                exp[rule.check].format(threshold=_fmt_number(rule.threshold or 0), unit=unit)
            ).strip()
        if rule.check == "ENUM_IN":
            return str(exp["ENUM_IN"].format(allowed=", ".join(rule.allowed or [])))
        return str(exp["CLAUSE_PRESENT"].format(category_label=self._cat(rule.category)))

    def _fields(self, rule: Rule, **extra: Any) -> dict[str, Any]:
        cfg = self._fact_cfg(rule.fact)
        return {
            "category_label": self._cat(rule.category),
            "fact_label": cfg.get("label", rule.fact),
            "fact_label_lower": str(cfg.get("label", rule.fact)).lower(),
            "unit": cfg.get("unit", ""),
            "threshold": _fmt_number(rule.threshold) if rule.threshold is not None else "",
            "allowed": ", ".join(rule.allowed or []),
            "expected": self._expected(rule),
            "applies_to": ", ".join(rule.applies_to),
            **extra,
        }

    def _reason(self, key: str, rule: Rule, **extra: Any) -> str:
        return " ".join(str(self.t["reasons"][key].format(**self._fields(rule, **extra))).split())

    # ----- evaluation ---------------------------------------------------------------------
    def evaluate(
        self, contract_type: str, clauses: Sequence[Clause], facts: dict[str, Fact]
    ) -> list[Finding]:
        index = _ClauseIndex([c for c in clauses if c.kind == "BODY"], self.embedder)
        findings = [
            self.evaluate_rule(r, contract_type, clauses, facts, index) for r in self.policy.rules
        ]
        position = {c.clause_id: i for i, c in enumerate(clauses)}
        return sorted(findings, key=lambda f: _sort_key(f, position))

    def evaluate_rule(
        self,
        rule: Rule,
        contract_type: str,
        clauses: Sequence[Clause],
        facts: dict[str, Fact],
        index: _ClauseIndex | None = None,
    ) -> Finding:
        def finding(
            status: Status,
            reason: str,
            evidence: Sequence[Clause] = (),
            found: str | None = None,
            evidence_text: str | None = None,
        ) -> Finding:
            severity: Severity | None = None
            if status in ("NON_COMPLIANT", "MISSING"):
                severity = rule.severity
            elif status == "NEEDS_REVIEW":
                severity = "LOW"
            return Finding(
                rule_id=rule.id,
                rule_name=rule.name,
                category=rule.category,
                status=status,
                severity=severity,
                expected=None if status == "NOT_APPLICABLE" else self._expected(rule),
                found=found,
                clause_ids=[c.clause_id for c in evidence],
                location=location(evidence),
                evidence_text=evidence_text,
                reason=reason,
            )

        # 1. contract type
        if contract_type not in rule.applies_to:
            return finding(
                "NOT_APPLICABLE",
                self._reason("not_applicable_type", rule, contract_type=contract_type),
            )

        # 2. clauses of the rule's category
        matched = [c for c in clauses if rule.category in c.categories and c.kind in RULE_KINDS]

        # 3. nothing classified: semantic search, then MISSING / NOT_APPLICABLE
        if not matched:
            index = index or _ClauseIndex([c for c in clauses if c.kind == "BODY"], self.embedder)
            best = index.best(rule.policy_text)
            if best is not None and best[1] >= self.tau_missing:
                clause, sim = best
                ref = clause.number or clause.clause_id
                return finding(
                    "NEEDS_REVIEW",
                    self._reason("semantic_candidate", rule, clause_ref=ref, similarity=sim),
                    evidence=[clause],
                    found=self.t["found"]["clause_absent"],
                    evidence_text=_excerpt(clause.text),
                )
            if rule.check == "CLAUSE_PRESENT" or rule.required_clause:
                return finding(
                    "MISSING", self._reason("missing", rule), found=self.t["found"]["clause_absent"]
                )
            return finding("NOT_APPLICABLE", self._reason("not_applicable_absent", rule))

        # 4. only low-confidence classifications
        if all(c.low_confidence for c in matched):
            return finding(
                "NEEDS_REVIEW",
                self._reason("low_confidence", rule),
                evidence=matched,
                evidence_text=_excerpt(matched[0].text),
            )

        # 5. presence check
        if rule.check == "CLAUSE_PRESENT":
            return finding(
                "COMPLIANT",
                self._reason("present", rule, location=location(matched)),
                evidence=matched,
                found=self.t["found"]["clause_present"],
                evidence_text=_excerpt(matched[0].text),
            )

        # 6. the fact
        fact = facts.get(rule.fact or "")
        by_id = {c.clause_id: c for c in clauses}
        evidence = [by_id[i] for i in (fact.clause_ids if fact else []) if i in by_id] or matched
        if fact is None or fact.ambiguous:
            return finding(
                "NEEDS_REVIEW",
                self._reason("ambiguous" if fact else "unextracted", rule),
                evidence=evidence,
                found=self.t["found"]["ambiguous" if fact else "unextracted"],
                evidence_text=fact.evidence_text if fact else None,
            )
        if fact.value is None:
            return finding(
                "NEEDS_REVIEW",
                self._reason("unextracted", rule),
                evidence=evidence,
                found=self.t["found"]["unextracted"],
                evidence_text=fact.evidence_text,
            )

        # 7. compare
        passed = compare(rule, fact.value)
        if passed is None:
            return finding(
                "NEEDS_REVIEW",
                self._reason("unextracted", rule),
                evidence=evidence,
                found=str(fact.value),
                evidence_text=fact.evidence_text,
            )
        found = self._value_text(rule, fact.value)
        key = f"{rule.check}_{'pass' if passed else 'fail'}"
        return finding(
            "COMPLIANT" if passed else "NON_COMPLIANT",
            self._reason(key, rule, found=found),
            evidence=evidence,
            found=found,
            evidence_text=fact.evidence_text,
        )


def compare(rule: Rule, value: bool | int | float | str) -> bool | None:
    """HLD 8.3 step 7. None when the value's type does not fit the check (bad policy or fact)."""
    if rule.check == "BOOLEAN_EQUALS":
        return value is rule.expected if isinstance(value, bool) else None
    if rule.check in ("NUMERIC_MIN", "NUMERIC_MAX"):
        if isinstance(value, bool) or not isinstance(value, int | float) or rule.threshold is None:
            return None
        return value >= rule.threshold if rule.check == "NUMERIC_MIN" else value <= rule.threshold
    if rule.check == "ENUM_IN":
        text = str(value).lower()
        return any(a.lower() in text for a in rule.allowed or [])
    return None


def _excerpt(text: str, limit: int = 400) -> str:
    """A verbatim prefix of the clause, cut at a word boundary."""
    if len(text) <= limit:
        return text
    cut = text.rfind(" ", 0, limit)
    return text[: cut if cut > 0 else limit]


def _sort_key(f: Finding, position: dict[str, int]) -> tuple[int, int, int, str]:
    first = min((position.get(i, 10**6) for i in f.clause_ids), default=10**6)
    return (STATUS_ORDER[f.status], SEVERITY_ORDER[f.severity], first, f.rule_id)


def evaluate_policy(
    policy: Policy,
    contract_type: str,
    clauses: Sequence[Clause],
    facts: dict[str, Fact],
    embedder: Embedder | None = None,
) -> list[Finding]:
    return PolicyEngine(policy, embedder).evaluate(contract_type, clauses, facts)
