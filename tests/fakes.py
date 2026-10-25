"""Test doubles shared by the classifier, pipeline and backend tests."""

from __future__ import annotations

import numpy as np

from contractguard.classification.classifier import ClauseClassifier, Prototypes
from contractguard.config import get_settings
from contractguard.llm.explainer import LLMCache
from contractguard.pipeline import Resources

KEYWORDS = {
    "CONFIDENTIALITY": ("confidential",),
    "TERMINATION": ("terminat",),
    "PAYMENT": ("invoice", "payment", "fees"),
    "LIABILITY": ("liabilit",),
    "INDEMNIFICATION": ("indemnif",),
    "IP": ("intellectual property",),
    "GOVERNING_LAW": ("governed by", "governing law"),
    "RENEWAL": ("renew",),
}
CATEGORIES = list(KEYWORDS)


class KeywordPipeline:
    """Stands in for the trained sklearn pipeline: probability 0.9 if a keyword occurs."""

    def predict_proba(self, texts):
        return np.array(
            [
                [0.9 if any(k in t.lower() for k in KEYWORDS[c]) else 0.05 for c in CATEGORIES]
                for t in texts
            ]
        )


class FakeEmbedder:
    """Bag-of-keywords vectors, so similarity is meaningful but deterministic."""

    VOCAB = ("uptime", "service level", "confidential", "terminat", "liabilit", "warrant")

    def encode(self, texts):
        rows = []
        for t in texts:
            v = np.array([float(w in t.lower()) for w in self.VOCAB] + [0.01])
            rows.append(v / np.linalg.norm(v))
        return np.array(rows)


def fake_classifier(embedder=None, prototypes=True) -> ClauseClassifier:
    protos = None
    if prototypes:
        e = FakeEmbedder()
        protos = Prototypes(["SLA"], e.encode(["uptime service level"]))
    return ClauseClassifier(
        KeywordPipeline(),
        CATEGORIES,
        dict.fromkeys(CATEGORIES, 0.5),
        protos,
        embedder,
        proto_threshold=0.5,
        model_name="keyword-fake",
    )


def fake_resources(provider=None, embedder=None) -> Resources:
    return Resources(
        classifier=fake_classifier(embedder),
        embedder=embedder,
        provider=provider,
        cache=LLMCache(),
        settings=get_settings(),
    )
