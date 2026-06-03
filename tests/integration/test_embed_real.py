"""Real sentence-transformers embedding (gated; needs `uv sync --extra embed` + model download)."""

from __future__ import annotations

import pytest

pytest.importorskip("sentence_transformers")

from ariadne.unstructured.embed import SentenceTransformerEmbedder

pytestmark = pytest.mark.integration


def test_real_embedder_returns_unit_dim_vectors() -> None:
    e = SentenceTransformerEmbedder()
    vecs = e.embed(["the shipment leaves at dawn", "quarterly budget review"])
    assert len(vecs) == 2 and len(vecs[0]) == e.dim == 384
    assert vecs[0] != vecs[1]
