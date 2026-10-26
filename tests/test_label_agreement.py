import importlib.util

from contractguard.config import REPO_ROOT

_spec = importlib.util.spec_from_file_location(
    "label_agreement", REPO_ROOT / "evaluation" / "label_agreement.py"
)
label_agreement = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(label_agreement)


def _gold():
    return {
        "contract_type": "NDA",
        "meta": {"effective_date": "2026-01-01", "expiry_date": None, "governing_law": "India"},
        "clauses": [
            {"number": None, "kind": "PREAMBLE", "categories": []},
            {"number": "1", "kind": "BODY", "categories": ["CONFIDENTIALITY"]},
            {"number": "2", "kind": "BODY", "categories": ["OTHER"]},
            {"number": None, "kind": "SIGNATURE", "categories": []},
        ],
        "facts": {"renewal.is_automatic": None, "governing_law.jurisdiction": "India"},
        "rules": {"R07": {"status": "COMPLIANT", "clauses": ["1"]}},
    }


def _second(**changes):
    second = {
        "contract_type": "NDA",
        "meta": {"effective_date": "2026-01-01", "expiry_date": None, "governing_law": "India"},
        "clauses": [
            ["PREAMBLE", "PREAMBLE", []],
            ["1", "BODY", ["CONFIDENTIALITY"]],
            ["2", "BODY", ["OTHER"]],
            ["SIGNATURE", "SIGNATURE", []],
        ],
        "facts": {"renewal.is_automatic": None, "governing_law.jurisdiction": "India"},
        "rules": {"R07": ["COMPLIANT", ["1"]]},
    }
    second.update(changes)
    return second


def test_identical_labels_agree_fully():
    row = label_agreement.compare("gc", _gold(), _second())
    assert row["disagreements"] == []
    assert row["boundaries"]["matched"] == 4
    assert row["facts"] == {"ok": 2, "n": 2}
    assert row["rules"] == {"ok": 1, "n": 1}


def test_disagreements_are_listed():
    second = _second(
        clauses=[
            ["PREAMBLE", "PREAMBLE", []],
            ["1", "BODY", ["CONFIDENTIALITY", "IP"]],
            ["SIGNATURE", "SIGNATURE", []],
        ],
        rules={"R07": ["MISSING", []]},
    )
    items = [d["item"] for d in label_agreement.compare("gc", _gold(), second)["disagreements"]]
    assert items == ["boundary 2", "categories 1", "rule R07"]


def test_kappa_undefined_for_one_value():
    assert label_agreement._kappa([0, 0], [0, 0]) is None
    assert label_agreement._kappa([0, 1], [0, 1]) == 1.0
