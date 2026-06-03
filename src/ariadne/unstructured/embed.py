"""Text embedding for the semantic retrieval leg (ADR-0007).

The ``Embedder`` is dependency-injected (like the HHEM ``EntailmentVerifier``)
so the core/tests stay hermetic via ``FakeEmbedder``; the real
``SentenceTransformerEmbedder`` lives behind the optional ``embed`` extra and is
lazy-imported (importlib) so the static checker stays stable without it. Default
model is the ungated ``bge-small-en-v1.5`` (384-dim, Apache-2.0); EmbeddingGemma-300m
(768-dim, gated) is a swap.
"""

from __future__ import annotations

import hashlib
from typing import Protocol


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FakeEmbedder:
    """Deterministic hash-based embedder for hermetic tests (no model)."""

    def __init__(self, dim: int = 8) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            vals = [b / 255.0 for b in digest]
            out.append([vals[i % len(vals)] for i in range(self.dim)])
        return out


_DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
_DEFAULT_DIM = 384


class SentenceTransformerEmbedder:
    """Real embedder via sentence-transformers (optional ``embed`` extra)."""

    def __init__(self, model: str = _DEFAULT_MODEL, dim: int = _DEFAULT_DIM) -> None:
        self.model_name = model
        self.dim = dim
        self._model = None

    def _load(self):
        if self._model is None:
            import importlib

            st = importlib.import_module("sentence_transformers")
            self._model = st.SentenceTransformer(self.model_name)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        vecs = self._load().encode(texts, normalize_embeddings=True)
        return [list(map(float, v)) for v in vecs]
