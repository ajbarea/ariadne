"""A ``DatasetAdapter`` driven by a frozen mapping (ADR-0020, the "apply" step).

Given a ratified ``Mapping`` and a ``RowReader`` (table name -> rows), this yields
canonical ``Entity`` / ``Relationship`` records, so the *existing* indexer, workup,
and eval run unchanged over a user's own store. The row reader is injected, so the
adapter is hermetic (fake rows in tests; a read-only psycopg reader in production).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from ariadne.datasets.canonical import Entity, Relationship

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator

    from ariadne.datasets.canonical import Canonical
    from ariadne.evaluation.needle import NeedleFixture
    from ariadne.mapping.schema import Mapping

    RowReader = Callable[[str], Iterable[dict]]


@dataclass
class MappingDrivenAdapter:
    """Project a user's tables onto the canonical schema via a ratified mapping."""

    name: str
    mapping: Mapping
    read_rows: RowReader
    access: Literal["public", "restricted"] = "restricted"
    entity_type: str = "entity"

    def load(self) -> Iterator[Canonical]:
        ent_by_table = {e.table: e for e in self.mapping.entities}
        for e in self.mapping.entities:
            for row in self.read_rows(e.table):
                yield Entity(
                    id=f"{e.type}:{row[e.id_column]}",
                    type=e.type,
                    name=str(row[e.name_column]),
                    attributes={
                        c: str(row[c]) for c in e.attribute_columns if row.get(c) is not None
                    },
                )
        for r in self.mapping.relationships:
            src_ent, dst_ent = ent_by_table.get(r.from_table), ent_by_table.get(r.to_table)
            if src_ent is None or dst_ent is None:
                continue  # validate_mapping rejects this; guard anyway
            for row in self.read_rows(r.from_table):
                fk = row.get(r.from_column)
                if fk is None:
                    continue
                yield Relationship(
                    src=f"{src_ent.type}:{row[src_ent.id_column]}",
                    dst=f"{dst_ent.type}:{fk}",
                    type=r.type,
                )

    def eval_fixtures(self) -> list[NeedleFixture]:
        return []  # user data has no planted-needle gold
