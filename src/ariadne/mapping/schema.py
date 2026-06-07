"""The frozen ``mapping.toml`` model + a deterministic structural validator (ADR-0020).

A mapping says how a user's introspected store projects onto Ariadne's canonical
schema: which tables are entities (and which column is the id / name / attributes),
and which foreign keys are relationships. The canonical ``type`` is an open string
(no "god model"), so validation checks *structure*, not a closed type list — every
referenced column must exist, and every relationship endpoint must itself be mapped
to an entity, so the result is actually loadable.

# research(2026-06): LLM schema-mapping's core failure is entities that "look right"
# but can't be loaded because an edge endpoint / cardinality is wrong — catch it with
# a deterministic validator before the mapping is ever applied (Schemora / OntoKG).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import tomli_w

if TYPE_CHECKING:
    from ariadne.introspect.postgres import SchemaSummary


@dataclass(frozen=True)
class EntityMapping:
    table: str
    type: str  # canonical entity type (open string: person | org | site | ...)
    id_column: str
    name_column: str
    attribute_columns: tuple[str, ...] = ()


@dataclass(frozen=True)
class RelationshipMapping:
    type: str  # canonical relationship type (MEMBER_OF | ...)
    from_table: str
    to_table: str
    from_column: str  # the FK column on from_table
    to_column: str  # the referenced column on to_table


@dataclass(frozen=True)
class Mapping:
    entities: tuple[EntityMapping, ...]
    relationships: tuple[RelationshipMapping, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DatasetHeader:
    """The ``[dataset]`` header that makes a frozen ``mapping.toml`` apply-able (ADR-0025).

    ``name`` is the dataset slug (``--dataset name``); ``dsn_env`` names the env var
    holding the read-only source connection string (kept off argv); ``schema`` is the
    Postgres schema the rows live in.
    """

    name: str
    dsn_env: str = "ARIADNE_SOURCE_DSN"
    schema: str = "public"


def validate_mapping(mapping: Mapping, summary: SchemaSummary) -> list[str]:
    """Return structural errors (empty list = valid + loadable).

    Checks: every entity table exists; every referenced column (id / name /
    attributes / FK endpoints) exists; every relationship endpoint table is itself
    mapped to an entity (else the edge cannot resolve to canonical ids).
    """
    errors: list[str] = []
    cols_by_table = {t: {c.name for c in cols} for t, cols in summary.tables.items()}
    mapped_tables = {e.table for e in mapping.entities}

    for e in mapping.entities:
        if e.table not in summary.tables:
            errors.append(f"entity table {e.table!r} is not in the schema")
            continue
        errors.extend(
            f"column {e.table}.{col!r} is not in the schema"
            for col in (e.id_column, e.name_column, *e.attribute_columns)
            if col not in cols_by_table[e.table]
        )

    for r in mapping.relationships:
        if r.from_table not in mapped_tables:
            errors.append(
                f"relationship {r.type!r} from_table {r.from_table!r} is not mapped to an entity"
            )
        if r.to_table not in mapped_tables:
            errors.append(
                f"relationship {r.type!r} to_table {r.to_table!r} is not mapped to an entity"
            )
        if r.from_table in cols_by_table and r.from_column not in cols_by_table[r.from_table]:
            errors.append(f"column {r.from_table}.{r.from_column!r} is not in the schema")
        if r.to_table in cols_by_table and r.to_column not in cols_by_table[r.to_table]:
            errors.append(f"column {r.to_table}.{r.to_column!r} is not in the schema")
    return errors


def dump_mapping_toml(mapping: Mapping, header: DatasetHeader | None = None) -> str:
    """Serialize a mapping to human-editable TOML (the draft a human ratifies).

    With a ``header``, prepends a ``[dataset]`` table so the draft is apply-able as a
    registered dataset once ratified (ADR-0025); without one, the structural-only
    form the validator/adapter already round-trip.
    """
    doc: dict = {}
    if header is not None:
        doc["dataset"] = {"name": header.name, "dsn_env": header.dsn_env, "schema": header.schema}
    doc |= {
        "entities": [
            {
                "table": e.table,
                "type": e.type,
                "id_column": e.id_column,
                "name_column": e.name_column,
                "attribute_columns": list(e.attribute_columns),
            }
            for e in mapping.entities
        ],
        "relationships": [
            {
                "type": r.type,
                "from_table": r.from_table,
                "to_table": r.to_table,
                "from_column": r.from_column,
                "to_column": r.to_column,
            }
            for r in mapping.relationships
        ],
    }
    return tomli_w.dumps(doc)


def load_mapping_toml(text: str) -> Mapping:
    """Parse a (possibly human-edited) ``mapping.toml`` back into a ``Mapping``."""
    doc = tomllib.loads(text)
    entities = tuple(
        EntityMapping(
            table=e["table"],
            type=e["type"],
            id_column=e["id_column"],
            name_column=e["name_column"],
            attribute_columns=tuple(e.get("attribute_columns", [])),
        )
        for e in doc.get("entities", [])
    )
    relationships = tuple(
        RelationshipMapping(
            type=r["type"],
            from_table=r["from_table"],
            to_table=r["to_table"],
            from_column=r["from_column"],
            to_column=r["to_column"],
        )
        for r in doc.get("relationships", [])
    )
    return Mapping(entities=entities, relationships=relationships)


def load_dataset_header(text: str) -> DatasetHeader | None:
    """Parse the optional ``[dataset]`` header, or ``None`` when the file has none."""
    d = tomllib.loads(text).get("dataset")
    if d is None:
        return None
    return DatasetHeader(
        name=d["name"],
        dsn_env=d.get("dsn_env", "ARIADNE_SOURCE_DSN"),
        schema=d.get("schema", "public"),
    )
