"""A user's declarative ontology + the check that a mapping speaks only it (ADR-0027).

An ontology is the user's **closed** vocabulary: the entity types their world has
and the relationship types that connect them, each routed ``domain -> range``.
Where ``schema.validate_mapping`` checks a mapping is *loadable* (columns exist,
edges resolve), ``validate_against_ontology`` checks it is *conformant* — every
entity typed as a declared type, every edge a declared type running between the
declared endpoints. The two compose: structural loadability, then vocabulary.

# research(2026-06): intrinsic-vs-relational routing as a declarative, portable
# schema (OntoKG arXiv:2604.02618); closed-vocabulary type assignment enforced by
# validation, SHACL-transpilable later (Anchor arXiv:2606.01208). ADR-0027.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ariadne.mapping.schema import Mapping


@dataclass(frozen=True)
class EntityType:
    name: str  # the user's domain entity type (e.g. Vessel, Indicator)
    description: str = ""


@dataclass(frozen=True)
class RelationshipType:
    name: str  # the user's domain edge type (e.g. MOORED_AT)
    domain: str  # the from entity-type name
    range: str  # the to entity-type name
    description: str = ""


@dataclass(frozen=True)
class Ontology:
    entity_types: tuple[EntityType, ...]
    relationship_types: tuple[RelationshipType, ...] = field(default_factory=tuple)

    @property
    def entity_type_names(self) -> frozenset[str]:
        return frozenset(e.name for e in self.entity_types)

    @property
    def relationship_type_names(self) -> frozenset[str]:
        return frozenset(r.name for r in self.relationship_types)

    @property
    def relationship_by_name(self) -> dict[str, RelationshipType]:
        return {r.name: r for r in self.relationship_types}


def load_ontology_toml(text: str) -> Ontology:
    """Parse a user-written ``ontology.toml`` into an ``Ontology``."""
    doc = tomllib.loads(text)
    entity_types = tuple(
        EntityType(name=e["name"], description=e.get("description", ""))
        for e in doc.get("entity_types", [])
    )
    relationship_types = tuple(
        RelationshipType(
            name=r["name"],
            domain=r["domain"],
            range=r["range"],
            description=r.get("description", ""),
        )
        for r in doc.get("relationship_types", [])
    )
    return Ontology(entity_types=entity_types, relationship_types=relationship_types)


def validate_against_ontology(mapping: Mapping, ontology: Ontology) -> list[str]:
    """Return conformance errors (empty = the mapping speaks only the ontology).

    Checks: every entity ``type`` is a declared entity type; every relationship
    ``type`` is a declared relationship type; and each edge obeys the declared
    routing — its ``from_table``'s entity type is the edge's ``domain``, its
    ``to_table``'s the ``range``. Endpoints not mapped to an entity are left to
    ``schema.validate_mapping`` (so a missing endpoint isn't double-reported here).
    """
    errors: list[str] = []
    entity_type_names = ontology.entity_type_names
    rel_by_name = ontology.relationship_by_name
    type_of_table = {e.table: e.type for e in mapping.entities}

    errors.extend(
        f"entity type {e.type!r} (table {e.table!r}) is not in the ontology"
        for e in mapping.entities
        if e.type not in entity_type_names
    )

    for r in mapping.relationships:
        declared = rel_by_name.get(r.type)
        if declared is None:
            errors.append(f"relationship type {r.type!r} is not in the ontology")
            continue
        from_type = type_of_table.get(r.from_table)
        to_type = type_of_table.get(r.to_table)
        if from_type is not None and from_type != declared.domain:
            errors.append(
                f"relationship {r.type!r} expects domain {declared.domain!r} but "
                f"{r.from_table!r} maps to {from_type!r}"
            )
        if to_type is not None and to_type != declared.range:
            errors.append(
                f"relationship {r.type!r} expects range {declared.range!r} but "
                f"{r.to_table!r} maps to {to_type!r}"
            )
    return errors
