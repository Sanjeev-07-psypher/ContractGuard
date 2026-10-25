import copy
import importlib.util
import json

import docx
import pytest
import yaml

from contractguard.config import REPO_ROOT

_spec = importlib.util.spec_from_file_location(
    "build_gold", REPO_ROOT / "evaluation" / "gold" / "build_gold.py"
)
build_gold = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_gold)

GOLD = REPO_ROOT / "evaluation" / "gold"
SOURCES = sorted(GOLD.glob("*/contract.yaml"))


@pytest.fixture(scope="module")
def policy():
    return json.loads((REPO_ROOT / "policies" / "default_vendor_v1.json").read_text())


def _load(name):
    return yaml.safe_load((GOLD / name / "contract.yaml").read_text(encoding="utf-8"))


def test_gold_set_composition():
    types = [yaml.safe_load(p.read_text())["contract_type"] for p in SOURCES]
    assert len(SOURCES) == 8
    assert sorted(types) == sorted(
        ["VENDOR_SERVICE"] * 3 + ["SAAS_LICENSE"] * 2 + ["NDA"] * 2 + ["OTHER"]
    )


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.parent.name)
def test_every_source_validates(path, policy):
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    build_gold.validate(spec, policy)
    body = [u for u in build_gold.units(spec) if u["kind"] == "BODY"]
    assert 10 <= len(body) <= 25  # HLD 12.2: 10-25 clauses per contract


def test_planted_issues_cover_hld_list():
    """HLD 12.2 names six planted issues; each must occur somewhere in the set."""
    facts = {p.parent.name: yaml.safe_load(p.read_text())["gold"]["facts"] for p in SOURCES}
    rules = {p.parent.name: yaml.safe_load(p.read_text())["gold"]["rules"] for p in SOURCES}
    assert any(f["termination.notice_days"] == 7 for f in facts.values())
    assert any(f["liability.is_uncapped"] for f in facts.values())
    assert any(f["renewal.is_automatic"] for f in facts.values())
    assert any(r["R06"]["status"] == "MISSING" for r in rules.values())
    assert any(
        f["governing_law.jurisdiction"] and "India" not in f["governing_law.jurisdiction"]
        for f in facts.values()
    )
    assert any(f["payment.due_days"] == 15 for f in facts.values())


def test_body_less_heading_merges_into_first_subclause():
    spec = _load("gc02")
    units = {u["number"]: u for u in build_gold.units(spec)}
    assert "12" not in units
    assert units["12.1"]["lines"][0] == "12. TERMINATION"
    assert units["12.1"]["heading"] == "Termination"
    assert units["12.2"]["heading"] is None
    assert units["12.2"]["section_path"] == "12 > 12.2"


def test_validate_rejects_unknown_category(policy):
    spec = copy.deepcopy(_load("gc01"))
    spec["clauses"][1]["categories"] = ["WARRANTY"]
    with pytest.raises(ValueError, match="unknown categories"):
        build_gold.validate(spec, policy)


def test_validate_rejects_status_for_rule_that_does_not_apply(policy):
    spec = copy.deepcopy(_load("gc06"))  # NDA: R03 does not apply
    spec["gold"]["rules"]["R03"] = {"status": "COMPLIANT", "clauses": ["8"]}
    with pytest.raises(ValueError, match="does not apply"):
        build_gold.validate(spec, policy)


def test_validate_rejects_missing_with_evidence(policy):
    spec = copy.deepcopy(_load("gc03"))
    spec["gold"]["rules"]["R06"] = {"status": "MISSING", "clauses": ["2"]}
    with pytest.raises(ValueError, match="must not cite"):
        build_gold.validate(spec, policy)


def test_validate_rejects_unknown_clause_reference(policy):
    spec = copy.deepcopy(_load("gc01"))
    spec["gold"]["rules"]["R03"]["clauses"] = ["99"]
    with pytest.raises(ValueError, match="unknown clause"):
        build_gold.validate(spec, policy)


def test_gold_json_shape():
    g = build_gold.gold_json(_load("gc07"))
    assert g["annotation"]["status"] == "DRAFT"
    assert g["clauses"][0]["kind"] == "PREAMBLE"
    article = next(c for c in g["clauses"] if c["number"] == "VII")
    assert article["categories"] == ["RENEWAL", "TERMINATION"]
    assert article["first_words"].startswith("ARTICLE VII - TERM AND RENEWAL")  # dash normalized
    assert set(g["rules"]) == {f"R{i:02d}" for i in range(1, 11)}


def test_auto_numbered_docx_has_numpr(tmp_path):
    out = tmp_path / "gc03.docx"
    build_gold.build_docx(_load("gc03"), out)
    paras = docx.Document(out).paragraphs
    levels = [
        p._p.pPr.numPr.ilvl.val
        for p in paras
        if p._p.pPr is not None and p._p.pPr.numPr is not None
    ]
    assert levels.count(0) == 14  # 14 numbered clause headings
    assert levels.count(1) == 3  # 10.1, 10.2, 10.3
    assert not any(p.text.startswith("10.1") for p in paras)  # numbers come from Word, not text
