"""Live smoke for the WorldSpeech HF streaming connector (needs the `data` extra)."""

from __future__ import annotations

import pytest

pytest.importorskip("datasets")  # skips unless the `data` extra is installed

from ariadne.datasets.canonical import Document
from ariadne.datasets.worldspeech import WorldSpeechAdapter

pytestmark = [pytest.mark.integration, pytest.mark.network]


def test_worldspeech_stream_yields_speech_documents() -> None:
    # Stream a tiny slice of one language-region config; proves the real corpus
    # is reachable and maps to speech_transcript documents.
    adapter = WorldSpeechAdapter(config="en_pk", limit=3)
    recs = list(adapter.load())
    docs = [r for r in recs if isinstance(r, Document)]
    assert docs, "expected at least one transcript document from the stream"
    assert all(d.modality == "speech_transcript" for d in docs)
    assert any(d.text.strip() for d in docs)
