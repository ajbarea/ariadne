"""Shared text helpers for the eval scorers (needle, reconciliation).

Marker scoring is substring presence over the lowercased note and the
concatenated ledger statements; ``statement_text`` makes that scan
connector-agnostic by joining every string-valued tool arg (Cypher lands under
``query``, postgres-mcp under ``sql``).
"""

from __future__ import annotations


def statement_text(entry: dict) -> str:
    """Join every string-valued tool arg of a ledger entry (connector-agnostic)."""
    tool_input = entry.get("tool_input", {})
    if not isinstance(tool_input, dict):
        return ""
    return "\n".join(v for v in tool_input.values() if isinstance(v, str))


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
