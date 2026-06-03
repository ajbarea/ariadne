from __future__ import annotations

from ariadne.datasets.canonical import Document, Entity, Relationship
from ariadne.datasets.enron import map_messages

_ROWS = [
    {
        "message_id": "m1",
        "from": "vince.kaminski@enron.com",
        "to": ["shirley.crenshaw@enron.com"],
        "cc": [],
        "subject": "models",
        "date": "2001-05-14T23:39:00",
        "body": "see attached",
        "file_name": "kaminski-v/sent/1.",
    },
    {
        "message_id": "m2",
        "from": "vince.kaminski@enron.com",
        "to": ["vkaminski@aol.com"],
        "cc": [],
        "subject": "fwd",
        "date": "2001-05-15T08:00:00",
        "body": "forwarding to myself",
        "file_name": "kaminski-v/sent/2.",
    },
    {
        "message_id": "m3",
        "from": "vince.kaminski@enron.com",
        "to": ["vkaminski@aol.com"],
        "cc": [],
        "subject": "fwd2",
        "date": "2001-05-16T08:00:00",
        "body": "again",
        "file_name": "kaminski-v/sent/3.",
    },
]


def test_addresses_become_person_entities() -> None:
    recs = list(map_messages(_ROWS))
    people = {r.name for r in recs if isinstance(r, Entity) and r.type == "person"}
    assert "vince.kaminski@enron.com" in people and "vkaminski@aol.com" in people


def test_emailed_edges_are_aggregated_with_a_count() -> None:
    recs = list(map_messages(_ROWS))
    aol = [
        r
        for r in recs
        if isinstance(r, Relationship)
        and r.type == "EMAILED"
        and r.dst == "person:vkaminski@aol.com"
    ]
    assert len(aol) == 1  # two messages collapse to one aggregated edge
    assert aol[0].attributes["count"] == "2"
    assert aol[0].src == "person:vince.kaminski@enron.com"


def test_bodies_become_email_documents() -> None:
    recs = list(map_messages(_ROWS))
    docs = [r for r in recs if isinstance(r, Document)]
    assert len(docs) == 3
    assert docs[0].modality == "email_body"
    assert docs[0].metadata["subject"] == "models"


def test_empty_addresses_are_skipped() -> None:
    rows = [
        {
            "message_id": "x",
            "from": "",
            "to": [""],
            "cc": [],
            "subject": "",
            "date": "",
            "body": "b",
            "file_name": "f",
        }
    ]
    recs = list(map_messages(rows))
    assert not any(isinstance(r, Entity) for r in recs)
    assert not any(isinstance(r, Relationship) for r in recs)
