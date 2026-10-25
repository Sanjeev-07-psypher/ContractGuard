"""Policy engine (HLD 8.3): one test per check type and per status branch."""

import numpy as np
import pytest

from contractguard.models import Clause, Fact
from contractguard.policy.engine import PolicyEngine, compare, location
from contractguard.policy.schema import Policy, Rule, load_policy


def clause(cid, cats=(), text="Some clause text.", kind="BODY", low=False, page=None, number=None):
    return Clause(
        clause_id=cid,
        number=number,
        text=text,
        section_path=number or cid,
        char_start=0,
        char_end=len(text),
        kind=kind,
        categories=list(cats),
        low_confidence=low,
        page_start=page,
        page_end=page,
    )


def rule(**kw):
    base = dict(
        id="R99",
        name="Test rule",
        category="TERMINATION",
        applies_to=["VENDOR_SERVICE"],
        check="NUMERIC_MIN",
        fact="termination.notice_days",
        threshold=30,
        severity="HIGH",
        policy_text="Termination for convenience needs 30 days' notice.",
        recommendation_template="Review the notice period.",
    )
    base.update(kw)
    return Rule(**base)


def engine(*rules, embedder=None, tau=None):
    policy = Policy(
        policy_id="t", name="t", version="1.0.0", rules=list(rules),
        thresholds={"tau_missing": tau},
    )  # fmt: skip
    return PolicyEngine(policy, embedder=embedder)


def run(r, clauses, facts=None, ctype="VENDOR_SERVICE", **kw):
    return engine(r, **kw).evaluate(ctype, clauses, facts or {})[0]


class FakeEmbedder:
    """Maps texts to fixed vectors: the policy text points at the clause containing 'uptime'."""

    def encode(self, texts):
        rows = []
        for t in texts:
            v = np.array([1.0, 0.0]) if ("uptime" in t or "SLA" in t) else np.array([0.0, 1.0])
            rows.append(v)
        return np.array(rows)


# --- step 1 -----------------------------------------------------------------------------------
def test_not_applicable_by_contract_type():
    f = run(rule(), [clause("c001", ["TERMINATION"])], ctype="NDA")
    assert f.status == "NOT_APPLICABLE" and f.severity is None
    assert "NDA" in f.reason


# --- step 3 -----------------------------------------------------------------------------------
def test_missing_when_clause_present_check_and_no_clause():
    f = run(rule(check="CLAUSE_PRESENT", fact=None, threshold=None, category="SLA"),
            [clause("c001", ["PAYMENT"])])  # fmt: skip
    assert f.status == "MISSING" and f.severity == "HIGH" and f.clause_ids == []


def test_missing_when_required_clause():
    f = run(rule(required_clause=True), [clause("c001", ["PAYMENT"])])
    assert f.status == "MISSING"


def test_not_applicable_when_absent_and_not_required():
    f = run(rule(), [clause("c001", ["PAYMENT"])])
    assert f.status == "NOT_APPLICABLE" and f.severity is None


def test_semantic_candidate_gives_needs_review():
    sla = rule(check="CLAUSE_PRESENT", fact=None, threshold=None, category="SLA",
               policy_text="An SLA with uptime commitments is required.")  # fmt: skip
    clauses = [clause("c001", ["PAYMENT"]), clause("c002", [], "Uptime: 99.5% uptime monthly.")]
    f = run(sla, clauses, embedder=FakeEmbedder(), tau=0.55)
    assert f.status == "NEEDS_REVIEW" and f.severity == "LOW"
    assert f.clause_ids == ["c002"] and "may cover it" in f.reason


def test_semantic_below_threshold_falls_back_to_missing():
    sla = rule(check="CLAUSE_PRESENT", fact=None, threshold=None, category="SLA",
               policy_text="Unrelated policy wording.")  # fmt: skip
    f = run(sla, [clause("c001", [], "uptime 99%.")], embedder=FakeEmbedder(), tau=0.55)
    assert f.status == "MISSING"


def test_semantic_search_ignores_non_body_clauses():
    sla = rule(check="CLAUSE_PRESENT", fact=None, threshold=None, category="SLA",
               policy_text="An SLA with uptime commitments is required.")  # fmt: skip
    clauses = [clause("c001", [], "uptime defined as ...", kind="DEFINITIONS")]
    assert run(sla, clauses, embedder=FakeEmbedder(), tau=0.55).status == "MISSING"


def test_definitions_clause_does_not_match_rule():
    f = run(rule(required_clause=True), [clause("c001", ["TERMINATION"], kind="DEFINITIONS")])
    assert f.status == "MISSING"


# --- step 4 -----------------------------------------------------------------------------------
def test_all_low_confidence_gives_needs_review():
    f = run(rule(), [clause("c001", ["TERMINATION"], low=True)],
            {"termination.notice_days": Fact(key="termination.notice_days", value=60)})  # fmt: skip
    assert f.status == "NEEDS_REVIEW" and f.severity == "LOW"


def test_one_confident_clause_is_enough():
    clauses = [clause("c001", ["TERMINATION"], low=True), clause("c002", ["TERMINATION"])]
    facts = {"termination.notice_days": Fact(key="termination.notice_days", value=60)}
    assert run(rule(), clauses, facts).status == "COMPLIANT"


# --- step 5 -----------------------------------------------------------------------------------
def test_clause_present_compliant():
    r = rule(check="CLAUSE_PRESENT", fact=None, threshold=None, category="CONFIDENTIALITY")
    f = run(r, [clause("c001", ["CONFIDENTIALITY"], "Each party shall keep it secret.", page=3)])
    assert f.status == "COMPLIANT" and f.severity is None
    assert f.location == "Page 3" and f.evidence_text == "Each party shall keep it secret."


# --- step 6 -----------------------------------------------------------------------------------
def test_fact_none_gives_needs_review():
    facts = {"termination.notice_days": Fact(key="termination.notice_days", value=None)}
    f = run(rule(), [clause("c001", ["TERMINATION"])], facts)
    assert f.status == "NEEDS_REVIEW" and f.found == "could not be determined"


def test_fact_absent_gives_needs_review():
    assert run(rule(), [clause("c001", ["TERMINATION"])]).status == "NEEDS_REVIEW"


def test_ambiguous_fact_gives_needs_review():
    fact = Fact(key="payment.due_days", value=None, ambiguous=True)
    r = rule(category="PAYMENT", fact="payment.due_days")
    f = run(r, [clause("c001", ["PAYMENT"])], {"payment.due_days": fact})
    assert f.status == "NEEDS_REVIEW" and f.found == "conflicting values"


# --- step 7, one per check type ---------------------------------------------------------------
@pytest.mark.parametrize("value,status", [(30, "COMPLIANT"), (7, "NON_COMPLIANT")])
def test_numeric_min(value, status):
    facts = {"termination.notice_days": Fact(key="termination.notice_days", value=value,
                                             clause_ids=["c001"], evidence_text="x")}  # fmt: skip
    f = run(rule(), [clause("c001", ["TERMINATION"], page=2)], facts)
    assert f.status == status
    assert f.expected == ">= 30 days" and f.found == f"{value} days"
    assert f.severity == ("HIGH" if status == "NON_COMPLIANT" else None)
    if status == "NON_COMPLIANT":
        assert f.reason == "Termination notice period is 7 days; policy requires at least 30 days."


@pytest.mark.parametrize("value,status", [(15, "COMPLIANT"), (45, "NON_COMPLIANT")])
def test_numeric_max(value, status):
    r = rule(check="NUMERIC_MAX", category="PAYMENT", fact="payment.due_days", threshold=30)
    facts = {"payment.due_days": Fact(key="payment.due_days", value=value)}
    f = run(r, [clause("c001", ["PAYMENT"])], facts)
    assert f.status == status and f.expected == "<= 30 days"


@pytest.mark.parametrize("value,status", [(True, "COMPLIANT"), (False, "NON_COMPLIANT")])
def test_boolean_equals(value, status):
    r = rule(check="BOOLEAN_EQUALS", category="LIABILITY", fact="liability.has_cap",
             expected=True, threshold=None)  # fmt: skip
    f = run(
        r,
        [clause("c001", ["LIABILITY"])],
        {"liability.has_cap": Fact(key="liability.has_cap", value=value)},
    )
    assert f.status == status
    assert f.expected == "liability is capped"


@pytest.mark.parametrize("value,status", [("India (Karnataka)", "COMPLIANT"),
                                          ("USA (New York)", "NON_COMPLIANT")])  # fmt: skip
def test_enum_in_substring_case_insensitive(value, status):
    r = rule(check="ENUM_IN", category="GOVERNING_LAW", fact="governing_law.jurisdiction",
             allowed=["india"], threshold=None, severity="MEDIUM")  # fmt: skip
    facts = {"governing_law.jurisdiction": Fact(key="governing_law.jurisdiction", value=value)}
    f = run(r, [clause("c001", ["GOVERNING_LAW"])], facts)
    assert f.status == status and f.found == value
    assert f.severity == ("MEDIUM" if status == "NON_COMPLIANT" else None)


def test_type_mismatch_gives_needs_review():
    facts = {"termination.notice_days": Fact(key="termination.notice_days", value="thirty")}
    assert run(rule(), [clause("c001", ["TERMINATION"])], facts).status == "NEEDS_REVIEW"


def test_compare_rejects_bool_for_numeric():
    assert compare(rule(), True) is None


# --- evidence, location, ordering -------------------------------------------------------------
def test_evidence_uses_fact_clauses():
    clauses = [clause("c001", ["TERMINATION"], page=1), clause("c002", ["TERMINATION"], page=4)]
    facts = {"termination.notice_days": Fact(key="termination.notice_days", value=7,
                                             clause_ids=["c002"])}  # fmt: skip
    f = run(rule(), clauses, facts)
    assert f.clause_ids == ["c002"] and f.location == "Page 4"


def test_location_formats():
    assert location([clause("a", page=2), clause("b", page=5)]) == "Pages 2-5"
    assert location([clause("a", number="9.1")]) == "Section 9.1"
    assert location([clause("a", number="9"), clause("b", number="10")]) == "Sections 9, 10"
    assert location([]) is None


def test_findings_sorted_by_status_then_severity():
    rules = [
        rule(id="R01", check="CLAUSE_PRESENT", fact=None, threshold=None, category="IP"),
        rule(id="R02", severity="LOW", required_clause=True, category="PAYMENT",
             fact="payment.due_days"),
        rule(id="R03"),
        rule(id="R04", severity="MEDIUM"),
    ]  # fmt: skip
    clauses = [clause("c001", ["TERMINATION", "IP"])]
    facts = {"termination.notice_days": Fact(key="termination.notice_days", value=7)}
    out = engine(*rules).evaluate("VENDOR_SERVICE", clauses, facts)
    assert [(f.rule_id, f.status) for f in out] == [
        ("R03", "NON_COMPLIANT"),
        ("R04", "NON_COMPLIANT"),
        ("R02", "MISSING"),
        ("R01", "COMPLIANT"),
    ]


def test_default_policy_is_deterministic():
    policy = load_policy("default_vendor_v1")
    clauses = [clause("c001", ["TERMINATION"]), clause("c002", ["CONFIDENTIALITY"])]
    facts = {"termination.notice_days": Fact(key="termination.notice_days", value=7)}
    a = PolicyEngine(policy).evaluate("VENDOR_SERVICE", clauses, facts)
    b = PolicyEngine(policy).evaluate("VENDOR_SERVICE", clauses, facts)
    assert [f.model_dump() for f in a] == [f.model_dump() for f in b]
    assert len(a) == 10
