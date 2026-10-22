from datetime import date, datetime

import pytest
from pydantic import ValidationError

from contractguard.models import (
    Block,
    Clause,
    ContractMeta,
    Document,
    Explanation,
    Fact,
    Finding,
    Party,
    Report,
)


def _clause(**kw):
    base = dict(
        clause_id="c001", text="7. Termination ...", section_path="7", char_start=0, char_end=18
    )
    base.update(kw)
    return Clause(**base)


def test_document_defaults_are_independent():
    d1 = Document(source_path="a.pdf", file_type="pdf", blocks=[Block(text="x", page=1)])
    d2 = Document(source_path="b.pdf", file_type="pdf", blocks=[])
    d1.warnings.append("w")
    assert d2.warnings == [] and d1.ocr_pages == []


def test_document_rejects_unknown_file_type():
    with pytest.raises(ValidationError):
        Document(source_path="a.txt", file_type="txt", blocks=[])


def test_clause_defaults():
    c = _clause()
    assert c.kind == "BODY" and c.classified_by == "none" and c.categories == []


def test_clause_rejects_bad_kind():
    with pytest.raises(ValidationError):
        _clause(kind="APPENDIX")


def test_fact_value_types():
    assert Fact(key="termination.notice_days", value=7, unit="days").value == 7
    assert Fact(key="liability.has_cap", value=True).value is True
    assert Fact(key="governing_law.jurisdiction", value="India (Karnataka)").value.startswith(
        "India"
    )


def test_finding_status_and_severity_enums():
    Finding(
        rule_id="R03",
        rule_name="n",
        category="TERMINATION",
        status="NON_COMPLIANT",
        severity="HIGH",
        reason="r",
    )
    with pytest.raises(ValidationError):
        Finding(rule_id="R03", rule_name="n", category="TERMINATION", status="RISKY", reason="r")
    with pytest.raises(ValidationError):
        Finding(
            rule_id="R03",
            rule_name="n",
            category="TERMINATION",
            status="MISSING",
            severity="CRITICAL",
            reason="r",
        )


def test_report_round_trip():
    expl = Explanation(
        summary="s",
        explanation="e",
        why_it_matters="w",
        suggested_review_action="a",
        quoted_evidence="",
        source="template",
        prompt_version="explain-v1",
    )
    report = Report(
        contract_id="abc",
        filename="x.pdf",
        meta=ContractMeta(
            contract_type="NDA",
            contract_type_source="auto",
            parties=[Party(name="ABC Technologies Pvt. Ltd.", alias="Company", role="OUR_ORG")],
            effective_date=date(2026, 4, 1),
        ),
        clauses=[_clause()],
        clause_checklist={"TERMINATION": True},
        findings=[
            Finding(
                rule_id="R07",
                rule_name="n",
                category="CONFIDENTIALITY",
                status="MISSING",
                severity="HIGH",
                reason="r",
                explanation=expl,
            )
        ],
        counts={"HIGH": 1},
        policy_id="default_vendor_v1",
        policy_version="1.0.0",
        pipeline_version="0.1.0",
        generated_at=datetime(2026, 10, 22, 6, 0),
        disclaimer="not legal advice",
    )
    again = Report.model_validate_json(report.model_dump_json())
    assert again == report
