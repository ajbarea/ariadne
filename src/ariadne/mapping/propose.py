"""Propose a schema->canonical mapping (ADR-0020, the "propose" step).

``SchemaMapper`` is the injection seam: a hermetic ``BaselineMapper`` (deterministic
heuristics, no model) ships now; an LLM-backed mapper lands later behind an extra,
the same way the rubric judge is injected. Either way the proposal is a *draft* a
human ratifies — nothing here is auto-applied.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from ariadne.mapping.schema import EntityMapping, Mapping, RelationshipMapping

if TYPE_CHECKING:
    from ariadne.introspect.postgres import Column, SchemaSummary

_NAME_HINTS = ("name", "title", "label", "full_name")


@runtime_checkable
class SchemaMapper(Protocol):
    def propose(self, summary: SchemaSummary) -> Mapping: ...


def _pick_id_column(table: str, cols: tuple[Column, ...]) -> str:
    names = [c.name for c in cols]
    if "id" in names:
        return "id"
    if f"{table}_id" in names:
        return f"{table}_id"
    return names[0]


def _pick_name_column(cols: tuple[Column, ...], id_column: str) -> str:
    for c in cols:
        if c.name.lower() in _NAME_HINTS:
            return c.name
    return id_column


def _singularize(table: str) -> str:
    return table[:-1] if len(table) > 1 and table.endswith("s") else table


def baseline_mapping(summary: SchemaSummary) -> Mapping:
    """A deterministic first-draft mapping: table -> entity, foreign key -> relationship.

    Heuristics (the human ratifies and renames): id column is ``id`` / ``<table>_id``
    / the first column; name column is the first name-like column else the id; the
    entity type is the naively singularized table name; attributes are the remaining
    columns minus the id, name, and foreign-key columns (FKs become relationships).
    """
    fk_cols_by_table: dict[str, set[str]] = {}
    for fk in summary.foreign_keys:
        fk_cols_by_table.setdefault(fk.from_table, set()).add(fk.from_column)

    entities = []
    for table, cols in summary.tables.items():
        id_col = _pick_id_column(table, cols)
        name_col = _pick_name_column(cols, id_col)
        excluded = {id_col, name_col} | fk_cols_by_table.get(table, set())
        attrs = tuple(c.name for c in cols if c.name not in excluded)
        entities.append(
            EntityMapping(
                table=table,
                type=_singularize(table),
                id_column=id_col,
                name_column=name_col,
                attribute_columns=attrs,
            )
        )

    relationships = tuple(
        RelationshipMapping(
            type=f"{fk.from_table}_{fk.to_table}".upper(),
            from_table=fk.from_table,
            to_table=fk.to_table,
            from_column=fk.from_column,
            to_column=fk.to_column,
        )
        for fk in summary.foreign_keys
    )
    return Mapping(entities=tuple(entities), relationships=relationships)


class BaselineMapper:
    """The deterministic ``SchemaMapper`` (no model); wraps ``baseline_mapping``."""

    def propose(self, summary: SchemaSummary) -> Mapping:
        return baseline_mapping(summary)
