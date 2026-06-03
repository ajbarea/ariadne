"""Canonical schema — the dataset-agnostic contract every adapter maps to.

Kept deliberately minimal (avoid the canonical "god model"): dataset-specific
fields live in the open ``attributes``/``metadata`` dicts, never as new core
fields. Each record maps to one store (see the indexer):
Entity/Relationship -> graph, Document -> full-text+vector(text)+relational(meta),
Attribute -> relational row.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Entity:
    id: str  # canonical, e.g. "person:Halberd"
    type: str  # person | org | unit | site | topic ...
    name: str
    aliases: tuple[str, ...] = ()
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Relationship:
    src: str  # Entity.id
    dst: str  # Entity.id
    type: str  # MEMBER_OF | EMAILED | CO_LOCATED ...
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Document:
    id: str
    text: str
    source_entity_ids: tuple[str, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)
    modality: str = "text"


@dataclass(frozen=True)
class Attribute:
    entity_id: str
    key: str
    value: str


Canonical = Entity | Relationship | Document | Attribute
