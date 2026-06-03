from __future__ import annotations

from ariadne.unstructured.embed import Embedder, FakeEmbedder


def test_fake_embedder_is_deterministic_and_fixed_dim() -> None:
    e: Embedder = FakeEmbedder(dim=8)
    v1 = e.embed(["hello world"])
    v2 = e.embed(["hello world"])
    assert v1 == v2  # deterministic
    assert len(v1) == 1 and len(v1[0]) == 8  # one vector, dim 8
    assert e.dim == 8


def test_fake_embedder_differs_by_text() -> None:
    e = FakeEmbedder(dim=8)
    assert e.embed(["a"])[0] != e.embed(["b"])[0]
