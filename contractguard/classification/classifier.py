"""Clause classification at inference time (HLD 6.4).

Order for each BODY / EXHIBIT clause:
1. trained classifier: categories with probability >= the category's tuned threshold;
2. SLA keyword rule (``patterns.yaml: sla_keywords``): adds SLA with ``classified_by="rule"``
   when the classifier found nothing else;
3. nothing yet: embedding fallback against category prototypes (including SLA); a match at or
   above ``embeddings.proto_threshold`` is kept with ``low_confidence=True``;
4. otherwise OTHER.

Other clause kinds (PREAMBLE, DEFINITIONS, SIGNATURE) are not classified.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from contractguard.config import Settings, get_patterns, get_settings
from contractguard.embeddings.service import Embedder, cosine_top_k
from contractguard.errors import ModelArtifactError
from contractguard.models import Clause

log = logging.getLogger(__name__)

CLASSIFIED_KINDS = frozenset({"BODY", "EXHIBIT"})


@dataclass
class Prototypes:
    categories: list[str]
    matrix: np.ndarray  # one normalised row per category


class ClauseClassifier:
    def __init__(
        self,
        pipeline: Any,
        categories: list[str],
        thresholds: dict[str, float],
        prototypes: Prototypes | None = None,
        embedder: Embedder | None = None,
        proto_threshold: float = 0.5,
        model_name: str = "unknown",
    ) -> None:
        self.pipeline = pipeline
        self.categories = categories
        self.thresholds = thresholds
        self.prototypes = prototypes
        self.embedder = embedder
        self.proto_threshold = proto_threshold
        self.model_name = model_name
        self.sla_patterns = [re.compile(p) for p in get_patterns()["sla_keywords"]]

    def predict_proba(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, len(self.categories)))
        return np.asarray(self.pipeline.predict_proba(list(texts)))

    def is_sla(self, text: str) -> bool:
        return any(p.search(text) for p in self.sla_patterns)

    def classify(self, clauses: Sequence[Clause]) -> list[Clause]:
        targets = [i for i, c in enumerate(clauses) if c.kind in CLASSIFIED_KINDS]
        probs = self.predict_proba([clauses[i].text for i in targets])
        out = [c.model_copy(update={"categories": [], "scores": {}}) for c in clauses]

        pending: list[int] = []
        for row, i in enumerate(targets):
            c = out[i]
            c.scores = {
                cat: round(float(p), 4) for cat, p in zip(self.categories, probs[row], strict=True)
            }
            c.categories = [
                cat for cat in self.categories if c.scores[cat] >= self.thresholds.get(cat, 0.5)
            ]
            c.classified_by = "classifier" if c.categories else "none"
            c.low_confidence = False
            if self.is_sla(c.text):
                c.categories.append("SLA")
                c.scores["SLA"] = 1.0
                if c.classified_by == "none":
                    c.classified_by = "rule"
            if not c.categories:
                pending.append(i)

        self._fallback([out[i] for i in pending])
        return out

    def _fallback(self, clauses: list[Clause]) -> None:
        if clauses and (self.prototypes is None or self.embedder is None):
            log.info("No prototypes/embedder: %d clauses default to OTHER", len(clauses))
        vectors = (
            self.embedder.encode([c.text for c in clauses])
            if clauses and self.prototypes is not None and self.embedder is not None
            else None
        )
        for n, c in enumerate(clauses):
            if vectors is not None and self.prototypes is not None:
                (k, sim), *_ = cosine_top_k(vectors[n], self.prototypes.matrix, k=1)
                if sim >= self.proto_threshold:
                    cat = self.prototypes.categories[k]
                    c.categories = [cat]
                    c.scores[cat] = max(c.scores.get(cat, 0.0), round(sim, 4))
                    c.classified_by = "embedding_fallback"
                    c.low_confidence = True
                    continue
            c.categories = ["OTHER"]
            c.classified_by = "none"


def artifact_paths(settings: Settings) -> dict[str, Path]:
    proto = settings.resolve_path(settings.embeddings.prototypes_path)
    return {
        "model": settings.resolve_path(settings.classification.model_path),
        "thresholds": settings.resolve_path(settings.classification.thresholds_path),
        "prototypes": proto,
        "prototype_categories": proto.with_suffix(".json"),
    }


def load_classifier(
    settings: Settings | None = None, embedder: Embedder | None = None
) -> ClauseClassifier:
    """Load the Phase 4 artifacts. Missing model or thresholds raise ``ModelArtifactError``;
    missing prototypes only disable the embedding fallback."""
    settings = settings or get_settings()
    paths = artifact_paths(settings)
    for key in ("model", "thresholds"):
        if not paths[key].is_file():
            raise ModelArtifactError(
                f"Classifier artifact missing: {paths[key]}. Train it first (see training/README)."
            )
    bundle = joblib.load(paths["model"])
    thresholds = json.loads(paths["thresholds"].read_text())
    prototypes = None
    if paths["prototypes"].is_file() and paths["prototype_categories"].is_file():
        prototypes = Prototypes(
            categories=json.loads(paths["prototype_categories"].read_text()),
            matrix=np.load(paths["prototypes"]),
        )
    return ClauseClassifier(
        pipeline=bundle["pipeline"],
        categories=list(bundle["categories"]),
        thresholds={k: float(v) for k, v in thresholds.items()},
        prototypes=prototypes,
        embedder=embedder,
        proto_threshold=settings.embeddings.proto_threshold,
        model_name=str(bundle.get("model_name", "unknown")),
    )
