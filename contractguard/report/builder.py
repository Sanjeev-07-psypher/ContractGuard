"""Assemble the final ``Report`` (HLD 5): checklist, counts, warnings, versions, disclaimer."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from contractguard import PIPELINE_VERSION
from contractguard.config import Settings, get_settings
from contractguard.models import CATEGORIES, Clause, ContractMeta, Document, Finding, Report
from contractguard.policy.engine import RULE_KINDS
from contractguard.policy.schema import Policy

COUNT_KEYS = (
    "HIGH",
    "MEDIUM",
    "LOW",
    "NON_COMPLIANT",
    "MISSING",
    "NEEDS_REVIEW",
    "COMPLIANT",
    "NOT_APPLICABLE",
    "CLAUSES",
)


def clause_checklist(clauses: Sequence[Clause]) -> dict[str, bool]:
    """Category -> present in at least one BODY / EXHIBIT clause (OTHER is not listed)."""
    present = {cat for c in clauses if c.kind in RULE_KINDS for cat in c.categories}
    return {cat: cat in present for cat in CATEGORIES if cat != "OTHER"}


def counts(findings: Sequence[Finding], clauses: Sequence[Clause]) -> dict[str, int]:
    """HIGH / MEDIUM / LOW count the issues (NON_COMPLIANT and MISSING) by severity; the status
    keys count findings; CLAUSES counts BODY and EXHIBIT clauses."""
    out = dict.fromkeys(COUNT_KEYS, 0)
    for f in findings:
        out[f.status] += 1
        if f.status in ("NON_COMPLIANT", "MISSING") and f.severity:
            out[f.severity] += 1
    out["CLAUSES"] = sum(c.kind in RULE_KINDS for c in clauses)
    return out


def build_report(
    *,
    contract_id: str,
    filename: str,
    doc: Document,
    meta: ContractMeta,
    clauses: Sequence[Clause],
    findings: Sequence[Finding],
    policy: Policy,
    executive_summary: str | None,
    warnings: Sequence[str],
    llm_used: bool,
    timings_s: dict[str, float],
    settings: Settings | None = None,
) -> Report:
    settings = settings or get_settings()
    return Report(
        contract_id=contract_id,
        filename=filename,
        meta=meta,
        clauses=list(clauses),
        clause_checklist=clause_checklist(clauses),
        findings=list(findings),
        counts=counts(findings, clauses),
        executive_summary=executive_summary,
        warnings=list(dict.fromkeys([*doc.warnings, *warnings])),
        policy_id=policy.policy_id,
        policy_version=policy.version,
        pipeline_version=PIPELINE_VERSION,
        generated_at=datetime.now(UTC),
        disclaimer=settings.disclaimer,
        file_type=doc.file_type,
        num_pages=doc.num_pages,
        ocr_pages=list(doc.ocr_pages),
        llm_used=llm_used,
        timings_s={k: round(v, 3) for k, v in timings_s.items()},
    )
