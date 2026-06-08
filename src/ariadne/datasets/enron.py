"""Enron email corpus (`corbt/enron-emails`) as a dataset adapter.

Deterministic header→graph + body→document mapping — no LLM (spec D3).
``map_messages`` is a pure transform (fabricated rows in tests); the adapter
class streams the real corpus in Task 2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from ariadne.datasets.base import register
from ariadne.datasets.canonical import Canonical, Document, Entity, Relationship
from ariadne.datasets.streaming import bounded_stream, stall_guarded, stall_timeout_s
from ariadne.evaluation.needle import FIXTURES, NeedleFixture, SupportingFact

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator


def _norm(addr: str) -> str:
    return (addr or "").strip().lower()


def _person_id(addr: str) -> str:
    return f"person:{addr}"


def map_messages(rows: Iterable[dict]) -> Iterator[Canonical]:
    """Map email rows to canonical records (entities, aggregated edges, documents).

    Edges between the same (sender, recipient) collapse to one ``EMAILED`` edge
    carrying ``count`` and ``first_seen``/``last_seen`` (ISO date strings).
    """
    people: dict[str, Entity] = {}
    edges: dict[tuple[str, str], dict[str, str]] = {}
    documents: list[Document] = []

    def _ensure(addr: str) -> str | None:
        norm = _norm(addr)
        if not norm:
            return None
        pid = _person_id(norm)
        people.setdefault(pid, Entity(id=pid, type="person", name=norm))
        return pid

    for row in rows:
        sender = _ensure(row.get("from", ""))
        recipients = [
            pid
            for a in (list(row.get("to") or []) + list(row.get("cc") or []))
            if (pid := _ensure(a))
        ]
        date = str(row.get("date") or "")
        if sender:
            for dst in recipients:
                edge = edges.setdefault(
                    (sender, dst), {"count": "0", "first_seen": "", "last_seen": ""}
                )
                edge["count"] = str(int(edge["count"]) + 1)
                if date:
                    if not edge["first_seen"] or date < edge["first_seen"]:
                        edge["first_seen"] = date
                    if date > edge["last_seen"]:
                        edge["last_seen"] = date
        documents.append(
            Document(
                id=f"email:{row.get('message_id', '')}",
                text=str(row.get("body") or ""),
                source_entity_ids=tuple(p for p in [sender, *recipients] if p),
                metadata={
                    "subject": str(row.get("subject") or ""),
                    "date": date,
                    "from": _norm(row.get("from", "")),
                    "file_name": str(row.get("file_name") or ""),
                },
                modality="email_body",
            )
        )

    yield from people.values()
    for (src, dst), attrs in edges.items():
        yield Relationship(src=src, dst=dst, type="EMAILED", attributes=attrs)
    yield from documents


_DATASET = "corbt/enron-emails"
_DEFAULT_MAILBOX = "kaminski-v"
_DEFAULT_LIMIT = 3000

# The non-obvious cross-account tie: Kaminski forwards work mail to a personal
# AOL address — the same person under a second identity, surfaced only by the
# communication pattern. Real-data analog of the synthetic Halberd↔Wren needle.
KAMINSKI_AOL_FIXTURE = NeedleFixture(
    entity="vince.kaminski@enron.com",
    answer_markers=("vkaminski@aol.com",),
    traversal_markers=("EMAILED",),
    min_hops=1,
    supporting_facts=(
        SupportingFact(note_markers=("vkaminski@aol.com",), ledger_markers=("EMAILED",)),
    ),
)
FIXTURES["kaminski-aol"] = KAMINSKI_AOL_FIXTURE


class EnronAdapter:
    """Streams `corbt/enron-emails`, optionally bounded to one mailbox, to canonical.

    ``mailbox`` filters by the `file_name` prefix (the demo default is
    ``kaminski-v`` — Vince Kaminski's mailbox); ``mailbox=None`` takes the first
    ``limit`` rows unfiltered (used by the fast integration test). Streaming
    avoids downloading all ~517K rows.
    """

    name: str = "enron"
    entity_type: str = "person"
    access: Literal["public", "restricted"] = "public"

    def __init__(self, mailbox: str | None = _DEFAULT_MAILBOX, limit: int = _DEFAULT_LIMIT) -> None:
        self.mailbox = mailbox
        self.limit = limit

    def _stream(self):
        # Lazy import via importlib so the static checker stays stable whether or
        # not the optional `data` extra is installed (mirrors provenance/entailment.py).
        import importlib

        load_dataset = importlib.import_module("datasets").load_dataset
        return load_dataset(_DATASET, split="train", streaming=True)

    def _rows(self):
        predicate = None
        if self.mailbox:
            prefix = f"{self.mailbox}/"

            def in_mailbox(row) -> bool:
                return str(row.get("file_name") or "").startswith(prefix)

            predicate = in_mailbox
        guarded = stall_guarded(self._stream, stall_timeout=stall_timeout_s())
        yield from bounded_stream(guarded, self.limit, predicate=predicate)

    def load(self):
        return map_messages(self._rows())

    def eval_fixtures(self) -> list[NeedleFixture]:
        return [KAMINSKI_AOL_FIXTURE]


register(EnronAdapter())
