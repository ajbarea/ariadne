"""Shared text helpers for the eval scorers (needle, reconciliation).

Marker scoring is substring presence over the lowercased note and the
concatenated ledger statements; ``statement_text`` makes that scan
connector-agnostic by joining every string-valued tool arg (Cypher lands under
``query``, postgres-mcp under ``sql``).
"""

from __future__ import annotations


def statement_text(entry: dict) -> str:
    """Join every string-valued tool arg of a ledger entry (connector-agnostic).

    The *action* only (query / sql). Used where intent matters — e.g.
    reconciliation's "both stores were queried". Trajectory grading uses
    ``traversal_text`` instead, which also reads the observation.
    """
    tool_input = entry.get("tool_input", {})
    if not isinstance(tool_input, dict):
        return ""
    return "\n".join(v for v in tool_input.values() if isinstance(v, str))


# Catalog/metadata calls whose OUTPUT describes the store's shape, not its contents
# — postgres-mcp catalog tools and Cypher schema procedures. Their observations must
# not count as traversal (a `CALL db.relationshipTypes()` lists every rel type, which
# would false-positive a guess). ADR-0024.
_SCHEMA_TOOLS = ("list_schemas", "list_objects", "get_object_details")
_SCHEMA_CYPHER = ("db.labels", "db.relationshiptypes", "db.propertykeys", "db.schema")


def is_schema_introspection(entry: dict) -> bool:
    """True for a catalog/metadata call (enumerate tables / labels / relationship
    types) rather than a retrieval over entity data. ADR-0024."""
    if any(t in entry.get("tool", "") for t in _SCHEMA_TOOLS):
        return True
    return any(s in statement_text(entry).lower() for s in _SCHEMA_CYPHER)


def traversal_text(entry: dict) -> str:
    """The action (query) plus, for a data-retrieval call, its observation.

    Trajectory and supporting-fact grading score the (action, observation) pair: a
    relationship type returned in the response proves the hop was *walked*, even when
    an untyped ``-[r]- RETURN type(r)`` query never names it. Schema-introspection
    observations are excluded so enumerating the catalog can't be mistaken for
    traversal. ``# research(2026-06): agentic-RAG trajectory eval grades observations,
    grounding judged vs what was retrieved (arXiv:2602.19127, 2603.07379). ADR-0024.``
    """
    parts = [statement_text(entry)]
    excerpt = entry.get("response_excerpt")
    if excerpt and not is_schema_introspection(entry):
        parts.append(str(excerpt))
    return "\n".join(parts)


def all_present(markers: tuple[str, ...], haystack_lower: str) -> bool:
    """True when every marker (case-insensitive) appears in ``haystack_lower``."""
    return all(m.lower() in haystack_lower for m in markers)


def any_present(markers: tuple[str, ...], haystack_lower: str) -> bool:
    """True when at least one marker (case-insensitive) appears in ``haystack_lower``."""
    return any(m.lower() in haystack_lower for m in markers)


def fraction_present(markers: tuple[str, ...], haystack_lower: str) -> float:
    """Fraction of markers (case-insensitive) present; 1.0 for an empty marker set."""
    if not markers:
        return 1.0
    found = sum(1 for m in markers if m.lower() in haystack_lower)
    return found / len(markers)
