from __future__ import annotations

from ariadne.datasets.canonical import Document, Entity
from ariadne.datasets.worldspeech import map_utterances

_ROWS = [
    {
        "segment_id": "uk-1",
        "human_transcript": "The honourable member's budget motion will carry.",
        "source": "UK Parliament",
        "source_url": "https://parliament.uk/clip/1",
        "session_date": "2020-03-11",
        "language": "en",
        "country": "GB",
        "duration": 4.1,
    },
    {
        "segment_id": "uk-2",
        "human_transcript": "We move to divide the House.",
        "source": "UK Parliament",
        "source_url": "https://parliament.uk/clip/2",
        "session_date": "2020-03-11",
        "language": "en",
        "country": "GB",
        "duration": 2.7,
    },
    {
        "segment_id": "bbc-1",
        "human_transcript": "Tonight's headlines from Westminster.",
        "source": "BBC",
        "source_url": "https://bbc.co.uk/clip/9",
        "session_date": "2020-03-11",
        "language": "en",
        "country": "GB",
        "duration": 3.0,
    },
]


def test_transcripts_become_speech_documents() -> None:
    recs = list(map_utterances(_ROWS))
    docs = [r for r in recs if isinstance(r, Document)]
    assert len(docs) == 3
    assert docs[0].modality == "speech_transcript"
    assert docs[0].text == "The honourable member's budget motion will carry."
    assert docs[0].metadata["country"] == "GB"
    assert docs[0].metadata["session_date"] == "2020-03-11"


def test_sources_become_deduped_org_entities() -> None:
    recs = list(map_utterances(_ROWS))
    orgs = [r for r in recs if isinstance(r, Entity) and r.type == "org"]
    names = {o.name for o in orgs}
    assert names == {"UK Parliament", "BBC"}  # two UK-Parliament rows collapse to one entity


def test_document_links_to_its_source_org() -> None:
    recs = list(map_utterances(_ROWS))
    doc = next(r for r in recs if isinstance(r, Document) and r.id.endswith("uk-1"))
    assert "org:UK Parliament" in doc.source_entity_ids


def test_empty_transcript_rows_are_skipped() -> None:
    rows = [{"segment_id": "x", "human_transcript": "  ", "source": "X", "country": "US"}]
    recs = list(map_utterances(rows))
    assert not any(isinstance(r, Document) for r in recs)
