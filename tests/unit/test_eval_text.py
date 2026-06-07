from __future__ import annotations

from ariadne.evaluation._text import (
    is_schema_introspection,
    statement_text,
    traversal_text,
)


def _entry(tool: str, query: str, excerpt: str) -> dict:
    return {"tool": tool, "tool_input": {"query": query}, "response_excerpt": excerpt}


# ── traversal_text: grade the (action, observation) pair (ADR-0024) ──


def test_traversal_text_includes_a_data_query_observation() -> None:
    # The live false-negative: an untyped `-[r]- RETURN type(r)` query walks the edge
    # but names the rel type only in the RESPONSE. Traversal must credit that.
    e = _entry(
        "mcp__neo4j__read_neo4j_cypher",
        "MATCH (h:Person {name:'Halberd'})-[r]-(o) RETURN type(r) AS rel",
        '[{"rel": "MEMBER_OF", "oname": "Signals-Cell"}]',
    )
    assert "MEMBER_OF" in traversal_text(e)


def test_traversal_text_excludes_schema_introspection_observation() -> None:
    # `CALL db.relationshipTypes()` returns the bare list of ALL rel types — enumerating
    # the catalog is not traversal, so its observation must NOT count (false-positive guard).
    e = _entry(
        "mcp__neo4j__read_neo4j_cypher",
        "CALL db.relationshipTypes() YIELD relationshipType RETURN collect(relationshipType)",
        '["MEMBER_OF", "CO_LOCATED", "REPORTS_TO"]',
    )
    assert "MEMBER_OF" not in traversal_text(e)  # only the query (the CALL) is scanned


def test_traversal_text_still_credits_a_typed_query_in_the_action() -> None:
    # A typed query names the marker in the action; that path still works.
    e = _entry("mcp__neo4j__read_neo4j_cypher", "MATCH (h)-[:MEMBER_OF]->(u) RETURN u", "rows")
    assert "MEMBER_OF" in traversal_text(e)


# ── is_schema_introspection: catalog/metadata calls, not traversal ──


def test_catalog_tools_are_schema_introspection() -> None:
    for tool in (
        "mcp__postgres__list_schemas",
        "mcp__postgres__list_objects",
        "mcp__postgres__get_object_details",
    ):
        assert is_schema_introspection({"tool": tool, "tool_input": {}}) is True


def test_cypher_schema_procedures_are_schema_introspection() -> None:
    for q in ("CALL db.labels()", "CALL db.relationshipTypes() YIELD x", "CALL db.propertyKeys()"):
        assert is_schema_introspection(
            {"tool": "mcp__neo4j__read_neo4j_cypher", "tool_input": {"query": q}}
        )


def test_a_data_query_is_not_schema_introspection() -> None:
    e = _entry(
        "mcp__neo4j__read_neo4j_cypher", "MATCH (h:Person {name:'Halberd'})-[r]-(o) RETURN r", "x"
    )
    assert is_schema_introspection(e) is False


# ── statement_text stays query-only (reconcile's "both stores queried" is unaffected) ──


def test_statement_text_is_query_only_not_the_observation() -> None:
    e = _entry(
        "mcp__neo4j__read_neo4j_cypher", "MATCH (h)-[r]-(o) RETURN type(r)", "MEMBER_OF in here"
    )
    assert "MEMBER_OF" not in statement_text(e)  # observation excluded; action only
    assert "MATCH" in statement_text(e)
