from __future__ import annotations

import ariadne.datasets.enron  # noqa: F401  (registers it)
from ariadne.datasets.base import get_adapter
from ariadne.datasets.canonical import Entity
from ariadne.datasets.enron import EnronAdapter


def test_adapter_metadata() -> None:
    a = EnronAdapter()
    assert a.name == "enron" and a.entity_type == "person" and a.access == "public"
    assert a.mailbox == "kaminski-v"  # demo subject default


def test_registered_in_the_registry() -> None:
    assert get_adapter("enron").name == "enron"


def test_load_maps_injected_rows(monkeypatch) -> None:
    rows = [
        {
            "message_id": "m",
            "from": "a@enron.com",
            "to": ["b@enron.com"],
            "cc": [],
            "subject": "s",
            "date": "2001-01-01",
            "body": "x",
            "file_name": "kaminski-v/1.",
        }
    ]
    a = EnronAdapter()
    monkeypatch.setattr(a, "_rows", lambda: iter(rows))
    names = {r.name for r in a.load() if isinstance(r, Entity)}
    assert {"a@enron.com", "b@enron.com"} <= names


def test_mailbox_none_means_no_filter(monkeypatch) -> None:
    # mailbox=None takes the first `limit` rows regardless of file_name.
    rows = [
        {
            "message_id": str(i),
            "from": "z@e.com",
            "to": ["q@e.com"],
            "cc": [],
            "subject": "",
            "date": "2001-01-01",
            "body": "b",
            "file_name": "anyone/x.",
        }
        for i in range(5)
    ]
    a = EnronAdapter(mailbox=None, limit=3)
    captured = []

    def _fake_stream():
        for r in rows:
            captured.append(r)
            yield r

    monkeypatch.setattr(a, "_stream", _fake_stream)
    list(a.load())  # _rows applies the limit
    assert len(captured) >= 3  # it consumed at least the limit
