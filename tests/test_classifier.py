"""Clause classifier inference (HLD 6.4) and training building blocks."""

import numpy as np
import pytest
from fakes import FakeEmbedder, fake_classifier
from sklearn.linear_model import LogisticRegression

from contractguard.classification.classifier import load_classifier
from contractguard.classification.features import NEGATIONS, MaskedOneVsRest, legal_stop_words
from contractguard.errors import ModelArtifactError
from contractguard.models import Clause


def clause(cid, text, kind="BODY"):
    return Clause(
        clause_id=cid, text=text, section_path=cid, char_start=0, char_end=len(text), kind=kind
    )


def test_classifier_threshold_and_kinds():
    out = fake_classifier().classify(
        [
            clause("c001", "This Agreement is between A and B.", kind="PREAMBLE"),
            clause("c002", "Either party may terminate on notice. Fees are payable."),
        ]
    )
    assert out[0].categories == [] and out[0].classified_by == "none"
    assert out[1].categories == ["TERMINATION", "PAYMENT"]
    assert out[1].classified_by == "classifier" and out[1].scores["TERMINATION"] == 0.9


def test_sla_rule_adds_category():
    out = fake_classifier().classify([clause("c001", "The Service Level for uptime is 99.5%.")])
    assert out[0].categories == ["SLA"] and out[0].classified_by == "rule"
    out = fake_classifier().classify([clause("c001", "Fees are paid per SLA credits.")])
    assert out[0].categories == ["PAYMENT", "SLA"] and out[0].classified_by == "classifier"


def test_embedding_fallback_low_confidence():
    clf = fake_classifier(FakeEmbedder())
    clf.sla_patterns = []  # force the fallback path
    out = clf.classify(
        [
            clause("c001", "Monthly uptime targets apply."),
            clause("c002", "Notices must be in writing."),
        ]
    )
    assert out[0].categories == ["SLA"] and out[0].low_confidence
    assert out[0].classified_by == "embedding_fallback"
    assert out[1].categories == ["OTHER"] and not out[1].low_confidence


def test_no_embedder_defaults_to_other():
    out = fake_classifier(None).classify([clause("c001", "Notices must be in writing.")])
    assert out[0].categories == ["OTHER"]


def test_missing_artifacts_raise(tmp_path):
    from contractguard.config import get_settings

    s = get_settings().model_copy(deep=True)
    s.classification.model_path = str(tmp_path / "none.joblib")
    with pytest.raises(ModelArtifactError):
        load_classifier(s)


def test_stop_words_keep_negations():
    words = set(legal_stop_words())
    assert "the" in words and not (NEGATIONS & words)


def test_masked_one_vs_rest_skips_unknown_rows():
    X = np.array([[0.0], [1.0], [0.0], [1.0], [5.0], [5.0]])
    # column 1: rows 4-5 are unknown (-1); if used as negatives they would flip the boundary
    Y = np.array([[0, 0], [1, 1], [0, 0], [1, 1], [1, -1], [1, -1]])
    m = MaskedOneVsRest(LogisticRegression()).fit(X, Y)
    p = m.predict_proba(np.array([[5.0]]))
    assert p.shape == (1, 2) and p[0, 1] > 0.5


def test_masked_one_vs_rest_constant_column():
    X = np.array([[0.0], [1.0]])
    m = MaskedOneVsRest(LogisticRegression()).fit(X, np.array([[0, -1], [1, -1]]))
    assert m.predict_proba(X)[:, 1].tolist() == [0.0, 0.0]
