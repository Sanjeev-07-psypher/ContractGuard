"""End-to-end orchestrator on a gold contract, with fake classifier/embedder and mocked LLM."""

import pytest
from fakes import FakeEmbedder, fake_resources

from contractguard.config import REPO_ROOT
from contractguard.llm.base import LLMError
from contractguard.llm.mock import MockProvider
from contractguard.pipeline import Options, run

GC01 = REPO_ROOT / "evaluation" / "gold" / "gc01"


@pytest.mark.parametrize("name", ["contract.docx", "contract_text.pdf"])
def test_run_produces_report(name):
    stages = []
    report = run(
        GC01 / name,
        Options(use_llm=False),
        fake_resources(),
        progress_cb=lambda s, p: stages.append((s, p)),
    )
    assert [s for s, _ in stages] == [
        "EXTRACTING",
        "SEGMENTING",
        "CLASSIFYING",
        "EVALUATING",
        "EXPLAINING",
        "DONE",
    ]
    assert report.meta.contract_type == "VENDOR_SERVICE" and len(report.findings) == 10
    assert report.counts["CLAUSES"] > 10 and report.disclaimer.startswith("ContractGuard")
    statuses = {f.rule_id: f.status for f in report.findings}
    assert statuses["R03"] == "NON_COMPLIANT"  # 7-day notice planted in gc01
    flagged = [
        f for f in report.findings if f.status in ("NON_COMPLIANT", "MISSING", "NEEDS_REVIEW")
    ]
    assert all(f.explanation and f.explanation.source == "template" for f in flagged)
    assert report.executive_summary and not report.llm_used
    assert set(report.timings_s) == {"extract", "segment", "classify", "evaluate", "explain"}


def test_deterministic_without_llm():
    a = run(GC01 / "contract.docx", Options(use_llm=False), fake_resources(), contract_id="x")
    b = run(GC01 / "contract.docx", Options(use_llm=False), fake_resources(), contract_id="x")
    skip = {"generated_at", "timings_s"}
    assert a.model_dump(exclude=skip) == b.model_dump(exclude=skip)


def test_user_contract_type_overrides():
    r = run(GC01 / "contract.docx", Options(contract_type="NDA", use_llm=False), fake_resources())
    assert r.meta.contract_type == "NDA" and r.meta.contract_type_source == "user"
    assert {f.rule_id: f.status for f in r.findings}["R03"] == "NOT_APPLICABLE"


def test_mock_llm_explanations_and_embeddings():
    r = run(GC01 / "contract.docx", Options(), fake_resources(MockProvider(), FakeEmbedder()))
    assert r.llm_used
    sources = {f.explanation.source for f in r.findings if f.explanation}
    assert "llm" in sources


def test_llm_down_still_produces_report():
    provider = MockProvider([LLMError("down", retryable=False)] * 50)
    r = run(GC01 / "contract.docx", Options(), fake_resources(provider))
    assert not r.llm_used and any("template" in w for w in r.warnings)
