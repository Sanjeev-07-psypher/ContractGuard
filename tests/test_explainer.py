"""LLM layer (HLD 9): grounding, number check, retries, cache, templates, ordering. All mocked."""

import json

import pytest

from contractguard.llm.base import LLMError
from contractguard.llm.explainer import (
    Explainer,
    LLMCache,
    RateLimiter,
    is_grounded,
    make_provider,
    unsupported_numbers,
)
from contractguard.llm.gemini import parse_json_object
from contractguard.llm.mock import MockProvider
from contractguard.llm.ollama import OllamaProvider
from contractguard.models import Clause, ContractMeta, Finding, Party
from contractguard.policy.schema import load_policy

CLAUSE = (
    "10.1 The Vendor may terminate this Agreement at any time by giving seven (7) days' "
    "prior written notice to the Company."
)
RULES = load_policy("default_vendor_v1").rules
R03 = next(r for r in RULES if r.id == "R03")


def finding(rule_id="R03", status="NON_COMPLIANT", severity="HIGH", clause_ids=("c010",)):
    return Finding(
        rule_id=rule_id,
        rule_name=f"Rule {rule_id}",
        category="TERMINATION",
        status=status,
        severity=severity,
        expected=">= 30 days",
        found="7 days" if status != "MISSING" else "no clause found",
        clause_ids=list(clause_ids) if status != "MISSING" else [],
        location="Page 4",
        evidence_text=CLAUSE if status != "MISSING" else None,
        reason="Termination notice period is 7 days; policy requires at least 30 days.",
    )


def good_answer(quote=CLAUSE, **kw):
    base = {
        "summary": "The Vendor can end the contract on 7 days' notice.",
        "explanation": "Policy needs 30 days; the clause gives 7.",
        "why_it_matters": "Short notice leaves little time to replace the vendor.",
        "suggested_review_action": "Check whether the notice can be extended.",
        "quoted_evidence": quote,
    }
    base.update(kw)
    return base


class NoSleep:
    def __init__(self):
        self.waits = []

    def __call__(self, s):
        self.waits.append(s)


def explainer(provider, **kw):
    sleep = NoSleep()
    ex = Explainer(provider, sleep=sleep, limiter=RateLimiter(1000, sleep=sleep), **kw)
    return ex, sleep


META = ContractMeta(
    contract_type="VENDOR_SERVICE",
    contract_type_source="auto",
    parties=[
        Party(name="ABC Technologies Pvt. Ltd.", alias="Company", role="OUR_ORG"),
        Party(name="Sharma Infotech", alias="Vendor", role="COUNTERPARTY"),
    ],
)
CLAUSES = [Clause(clause_id="c010", number="10.1", text=CLAUSE, section_path="10 > 10.1",
                  char_start=0, char_end=len(CLAUSE), categories=["TERMINATION"])]  # fmt: skip


# --- grounding ------------------------------------------------------------------------------
def test_grounding_normalizes_whitespace():
    assert is_grounded("seven (7)  days'\nprior written notice", CLAUSE, "NON_COMPLIANT")
    assert not is_grounded("thirty (30) days", CLAUSE, "NON_COMPLIANT")
    assert not is_grounded("", CLAUSE, "NON_COMPLIANT")


def test_grounding_missing_requires_empty_quote():
    assert is_grounded("", "", "MISSING")
    assert not is_grounded("anything", "", "MISSING")


def test_unsupported_numbers():
    assert unsupported_numbers(good_answer(), "7 days vs 30 days") == []
    assert unsupported_numbers(good_answer(explanation="It gives 45 days."), "7 and 30") == ["45"]


# --- explain one finding --------------------------------------------------------------------
def test_llm_explanation_used_when_grounded():
    ex, _ = explainer(MockProvider([good_answer()]))
    e = ex.explain(finding(), R03, CLAUSE, "VENDOR_SERVICE", "Company", "Vendor")
    assert e.source == "llm" and e.model == "mock-1" and e.prompt_version == "explain-v1"
    assert e.quoted_evidence == CLAUSE


def test_prompt_contains_rule_and_clause_only():
    provider = MockProvider([good_answer()])
    ex, _ = explainer(provider)
    ex.explain(finding(), R03, CLAUSE, "VENDOR_SERVICE", "Company", "Vendor")
    system, user = provider.calls[0]
    assert "do not give legal advice" in system.lower()
    assert "status=NON_COMPLIANT, severity=HIGH" in user and CLAUSE in user
    assert "Our organization is referred to as: Company; counterparty: Vendor" in user


def test_ungrounded_quote_retried_once_then_template():
    provider = MockProvider([good_answer("made up"), good_answer("still made up")])
    ex, _ = explainer(provider)
    e = ex.explain(finding(), R03, CLAUSE, "VENDOR_SERVICE", "Company", "Vendor")
    assert e.source == "template" and len(provider.calls) == 2
    assert "copied exactly" in provider.calls[1][1]
    assert ex.stats["grounding_failures"] == 2


def test_ungrounded_then_grounded_uses_llm():
    ex, _ = explainer(MockProvider([good_answer("made up"), good_answer()]))
    e = ex.explain(finding(), R03, CLAUSE, "VENDOR_SERVICE", "Company", "Vendor")
    assert e.source == "llm"


def test_hallucinated_number_rejected():
    bad = good_answer(explanation="The notice is 14 days.")
    ex, _ = explainer(MockProvider([bad, bad]))
    e = ex.explain(finding(), R03, CLAUSE, "VENDOR_SERVICE", "Company", "Vendor")
    assert e.source == "template" and ex.stats["number_failures"] == 2


def test_missing_finding_sends_no_clause_and_needs_empty_quote():
    answer = good_answer(quote="", summary="No termination clause.", explanation="Not found.")
    provider = MockProvider([answer])
    ex, _ = explainer(provider)
    e = ex.explain(finding(status="MISSING"), R03, "", "VENDOR_SERVICE", "Company", "Vendor")
    assert e.source == "llm" and e.quoted_evidence == ""
    assert "No clause covering this rule was found" in provider.calls[0][1]


def test_retryable_errors_back_off_then_succeed():
    provider = MockProvider([LLMError("429", retryable=True), LLMError("503", True), good_answer()])
    ex, sleep = explainer(provider)
    e = ex.explain(finding(), R03, CLAUSE, "VENDOR_SERVICE", "Company", "Vendor")
    assert e.source == "llm" and sleep.waits[-2:] == [2.0, 4.0]


def test_retries_exhausted_falls_back_to_template():
    provider = MockProvider([LLMError("429", retryable=True)] * 3)
    ex, sleep = explainer(provider)
    e = ex.explain(finding(), R03, CLAUSE, "VENDOR_SERVICE", "Company", "Vendor")
    assert e.source == "template" and len(provider.calls) == 3 and sleep.waits == [2.0, 4.0]


def test_non_retryable_error_is_not_retried():
    provider = MockProvider([LLMError("400 bad request")])
    ex, _ = explainer(provider)
    e = ex.explain(finding(), R03, CLAUSE, "VENDOR_SERVICE", "Company", "Vendor")
    assert e.source == "template" and len(provider.calls) == 1


def test_malformed_answer_falls_back():
    ex, _ = explainer(MockProvider([{"summary": 1}, {"summary": "x"}]))
    e = ex.explain(finding(), R03, CLAUSE, "VENDOR_SERVICE", "Company", "Vendor")
    assert e.source == "template"


def test_cache_hit_skips_provider(tmp_path):
    cache = LLMCache(tmp_path / "c.db")
    provider = MockProvider([good_answer()])
    ex, _ = explainer(provider, cache=cache)
    ex.explain(finding(), R03, CLAUSE, "VENDOR_SERVICE", "Company", "Vendor")
    ex2, _ = explainer(MockProvider([]), cache=LLMCache(tmp_path / "c.db"))
    e = ex2.explain(finding(), R03, CLAUSE, "VENDOR_SERVICE", "Company", "Vendor")
    assert e.source == "llm" and ex2.stats["cache_hits"] == 1


def test_cache_key_changes_with_inputs():
    k = LLMCache.make_key("explain-v1", "R03", "NON_COMPLIANT", CLAUSE, ">= 30", "7", "m")
    assert k != LLMCache.make_key("explain-v1", "R03", "NON_COMPLIANT", CLAUSE, ">= 30", "8", "m")
    assert k != LLMCache.make_key("explain-v2", "R03", "NON_COMPLIANT", CLAUSE, ">= 30", "7", "m")


def test_template_when_no_provider():
    ex, _ = explainer(None)
    e = ex.explain(finding(), R03, CLAUSE, "VENDOR_SERVICE", "Company", "Vendor")
    assert e.source == "template" and e.suggested_review_action == R03.recommendation_template
    assert e.why_it_matters == R03.policy_text and e.quoted_evidence == CLAUSE


def test_template_missing_has_empty_quote():
    e = explainer(None)[0].template_explanation(finding(status="MISSING"), R03)
    assert e.quoted_evidence == "" and "not found" in e.explanation


# --- whole report ---------------------------------------------------------------------------
def test_only_flagged_findings_are_explained_and_capped(monkeypatch):
    findings = [
        finding("R03", "NON_COMPLIANT", "HIGH"),
        finding("R04", "NEEDS_REVIEW", "LOW"),
        finding("R05", "NON_COMPLIANT", "MEDIUM"),
        finding("R07", "COMPLIANT", None),
    ]
    ex, _ = explainer(MockProvider())
    monkeypatch.setattr(ex.settings.llm, "max_findings", 2)
    out = ex.explain_findings(findings, RULES, CLAUSES, META)
    assert [f.explanation.source if f.explanation else None for f in out] == [
        "llm", "template", "llm", None,
    ]  # fmt: skip
    assert [f.status for f in out] == [f.status for f in findings]  # status never changes
    assert [f.severity for f in out] == [f.severity for f in findings]


def test_executive_summary_llm_and_template():
    findings = [finding()]
    ex, _ = explainer(MockProvider())
    assert (
        ex.executive_summary(findings, "VENDOR_SERVICE") == "Mock overview of the flagged findings."
    )
    t = explainer(None)[0].executive_summary(findings, "VENDOR_SERVICE")
    assert t.startswith("ContractGuard checked 1 policy rules: 1 not met") and "Rule R03" in t


def test_executive_summary_rejects_invented_numbers():
    ex, _ = explainer(MockProvider([{"executive_summary": "There are 99 problems."}]))
    assert ex.executive_summary([finding()], "VENDOR_SERVICE").startswith("ContractGuard checked")


def test_rate_limiter_waits_when_bucket_empty():
    now = [0.0]
    sleep = NoSleep()
    rl = RateLimiter(2, clock=lambda: now[0], sleep=sleep)
    rl.acquire()
    rl.acquire()
    rl.acquire()
    assert sleep.waits == [pytest.approx(30.0)]


# --- providers ------------------------------------------------------------------------------
def test_parse_json_object_handles_fence():
    assert parse_json_object('```json\n{"a": "b"}\n```') == {"a": "b"}
    with pytest.raises(LLMError):
        parse_json_object("[1, 2]")
    with pytest.raises(LLMError):
        parse_json_object("not json")


def test_ollama_unreachable_is_retryable():
    with pytest.raises(LLMError) as e:
        OllamaProvider("llama3.1:8b", host="http://127.0.0.1:9").generate_json(
            "s", "u", {}, timeout_s=1
        )
    assert e.value.retryable


def test_make_provider(monkeypatch):
    from contractguard.config import get_settings

    s = get_settings().model_copy(deep=True)
    s.llm.provider = "none"
    assert make_provider(s) is None
    s.llm.provider = "mock"
    assert isinstance(make_provider(s), MockProvider)
    s.llm.provider, s.llm.model, s.gemini_api_key = "gemini", "some-flash-model", None
    assert make_provider(s) is None  # no key: templates
    s.llm.provider = "ollama"
    assert isinstance(make_provider(s), OllamaProvider)


def test_mock_default_answer_is_grounded():
    ex, _ = explainer(MockProvider())
    e = ex.explain(finding(), R03, CLAUSE, "VENDOR_SERVICE", "Company", "Vendor")
    assert e.source == "llm" and is_grounded(e.quoted_evidence, CLAUSE, "NON_COMPLIANT")
    json.dumps(e.model_dump())
