"""Building blocks for the clause classifier (HLD 6.4) that must be importable at inference time,
because ``models/classifier.joblib`` pickles references to them.

* ``legal_stop_words``: sklearn's English list minus negation words (HLD 6.2, 6.4).
* ``MaskedOneVsRest``: multi-label one-vs-rest where a label of -1 means "unknown" (D39).
  CUAD has no CONFIDENTIALITY labels, so a CUAD paragraph is neither a positive nor a negative
  example for that class; it is left out of that class's training rows.
* ``MiniLMEncoder``: sentence-embedding features for the MiniLM + LR comparison model.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin, TransformerMixin, clone
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

NEGATIONS = frozenset(
    {"no", "not", "nor", "never", "none", "without", "unless", "except", "notwithstanding"}
)


def legal_stop_words() -> list[str]:
    return sorted(set(ENGLISH_STOP_WORDS) - NEGATIONS)


class MaskedOneVsRest(ClassifierMixin, BaseEstimator):
    """One binary ``estimator`` per column of ``Y``; rows where ``Y[:, k] == -1`` are skipped
    for column ``k``. A column with a single class seen gets a constant prediction."""

    def __init__(self, estimator: Any) -> None:
        self.estimator = estimator

    def fit(self, X: Any, Y: np.ndarray) -> MaskedOneVsRest:
        Y = np.asarray(Y)
        self.estimators_: list[Any] = []
        self.constant_: list[float | None] = []
        for k in range(Y.shape[1]):
            rows = np.flatnonzero(Y[:, k] != -1)
            y = Y[rows, k]
            if len(np.unique(y)) < 2:
                self.estimators_.append(None)
                self.constant_.append(float(y[0]) if len(y) else 0.0)
                continue
            self.estimators_.append(clone(self.estimator).fit(X[rows], y))
            self.constant_.append(None)
        self.n_outputs_ = Y.shape[1]
        return self

    def predict_proba(self, X: Any) -> np.ndarray:
        n = X.shape[0]
        out = np.zeros((n, self.n_outputs_))
        for k, (est, const) in enumerate(zip(self.estimators_, self.constant_, strict=True)):
            if est is None:
                out[:, k] = const if const is not None else 0.0
            else:
                proba = est.predict_proba(X)
                pos = list(est.classes_).index(1)
                out[:, k] = proba[:, pos]
        return out

    def predict(self, X: Any) -> np.ndarray:
        return (self.predict_proba(X) >= 0.5).astype(int)


class MiniLMEncoder(TransformerMixin, BaseEstimator):
    """Text -> L2-normalised MiniLM embedding. The model is loaded lazily and not pickled."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        self.model_name = model_name

    def fit(self, X: Any, y: Any = None) -> MiniLMEncoder:
        return self

    def transform(self, X: Any) -> np.ndarray:
        from contractguard.embeddings.service import EmbeddingService

        if not hasattr(self, "_service"):
            self._service = EmbeddingService(self.model_name)
        return self._service.encode([str(x) for x in X])

    def __getstate__(self) -> dict[str, Any]:
        state = dict(self.__dict__)
        state.pop("_service", None)
        return state
