"""Live Enron load from Hugging Face (gated; needs `uv sync --extra data` + network)."""

from __future__ import annotations

import pytest

pytest.importorskip("datasets")  # skips unless the `data` extra is installed

from ariadne.datasets.canonical import Document, Entity, Relationship
from ariadne.datasets.enron import EnronAdapter

pytestmark = [pytest.mark.integration, pytest.mark.network]


def test_streams_real_corpus_into_canonical_records() -> None:
    # mailbox=None + small limit keeps this fast (no scan to find a mailbox).
    recs = list(EnronAdapter(mailbox=None, limit=100).load())
    assert any(isinstance(r, Entity) and r.type == "person" for r in recs)
    assert any(isinstance(r, Relationship) and r.type == "EMAILED" for r in recs)
    assert any(isinstance(r, Document) and r.modality == "email_body" for r in recs)
