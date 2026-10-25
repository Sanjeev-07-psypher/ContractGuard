import importlib.util

from contractguard.config import REPO_ROOT

_spec = importlib.util.spec_from_file_location(
    "inspect_labels", REPO_ROOT / "training" / "inspect_labels.py"
)
inspect_labels = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(inspect_labels)


def test_unknown_names():
    mapping = {"PAYMENT": ["Payments", "Fees"], "IP": ["Intellectual Property"]}
    assert inspect_labels.unknown_names(mapping, ["Payments", "Intellectual Property"]) == ["Fees"]


def test_cuad_question_regex():
    q = (
        'Highlight the parts (if any) of this contract related to "Cap On Liability" that '
        "should be reviewed by a lawyer."
    )
    assert inspect_labels.CUAD_QUESTION.search(q).group("cat") == "Cap On Liability"


def test_main_writes_files_and_flags_unknown(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(inspect_labels, "ledgar_labels", lambda: ["Confidentiality", "Payments"])
    monkeypatch.setattr(inspect_labels, "cuad_labels", lambda: ["Governing Law"])
    monkeypatch.setattr(
        inspect_labels,
        "get_label_map",
        lambda: {"ledgar": {"PAYMENT": ["Payments", "Fees"]}, "cuad": {"GOVERNING_LAW": []}},
    )
    assert inspect_labels.main(["--out-dir", str(tmp_path)]) == 1
    assert (tmp_path / "labels_ledgar.txt").read_text().splitlines() == [
        "Confidentiality",
        "Payments",
    ]
    assert "'Fees'" in capsys.readouterr().out
