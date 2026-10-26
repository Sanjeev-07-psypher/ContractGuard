"""Sentence embeddings and cosine top-k (HLD 6.4 fallback, 8.3 step 3, E6).

MiniLM (``embeddings.model_name``) is loaded once, lazily. Vectors are L2-normalised, so cosine
similarity is a dot product; a plain numpy matrix replaces a vector database (HLD 0.6).
Anything with an ``encode(texts) -> ndarray`` method satisfies ``Embedder``; tests pass a fake.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Protocol

import numpy as np

from contractguard.config import Settings, get_settings

log = logging.getLogger(__name__)


class Embedder(Protocol):
    def encode(self, texts: list[str]) -> np.ndarray:
        """Return one L2-normalised row per text, shape (len(texts), dim)."""
        ...


def normalize_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.where(norms == 0, 1.0, norms)


def cosine_top_k(query: np.ndarray, matrix: np.ndarray, k: int = 3) -> list[tuple[int, float]]:
    """Indices and similarities of the ``k`` rows of ``matrix`` closest to ``query``.

    Both inputs must already be normalised. Ties keep the lower index (stable sort), so the result
    is deterministic.
    """
    if matrix.size == 0:
        return []
    sims = matrix @ query
    order = np.argsort(-sims, kind="stable")[:k]
    return [(int(i), float(sims[i])) for i in order]


class EmbeddingService:
    """Thread-safe lazy wrapper around ``SentenceTransformer``."""

    def __init__(self, model_name: str | None = None, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        self.model_name = model_name or settings.embeddings.model_name
        self._model: Any = None
        self._lock = threading.Lock()

    def _load(self) -> Any:
        with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer

                log.info("Loading embedding model %s", self.model_name)
                try:  # use the local cache first, so no network call when already downloaded
                    self._model = SentenceTransformer(
                        self.model_name, device="cpu", local_files_only=True
                    )
                except Exception:
                    self._model = SentenceTransformer(self.model_name, device="cpu")
        return self._model

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        vectors = self._load().encode(
            texts, batch_size=32, convert_to_numpy=True, normalize_embeddings=True
        )
        return np.asarray(vectors, dtype=np.float32)


def try_load_embedder(settings: Settings | None = None) -> EmbeddingService | None:
    """Return a loaded service, or None (with a log line) if the model cannot be loaded.

    The pipeline then skips the semantic steps and adds a warning instead of failing (HLD 16).
    """
    service = EmbeddingService(settings=settings)
    try:
        service.encode(["warm up"])
    except Exception as exc:  # model missing offline, download blocked, ...
        log.warning("Embedding model unavailable (%s): semantic checks are skipped", exc)
        return None
    return service
