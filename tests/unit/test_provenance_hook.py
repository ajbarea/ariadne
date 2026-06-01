from __future__ import annotations

import pytest

from ariadne.provenance.hook import make_provenance_hook
from ariadne.provenance.ledger import ProvenanceLedger


@pytest.mark.asyncio
async def test_hook_records_graph_calls_and_returns_cite_context() -> None:
    led = ProvenanceLedger()
    hook = make_provenance_hook(led)
    out = await hook(
        {
            "tool_name": "mcp__neo4j__read_neo4j_cypher",
            "tool_input": {"query": "MATCH (n) RETURN n"},
            "tool_response": "rows...",
        },
        "tool-use-1",
        None,
    )
    assert led.has("g1")
    # The hook tells the agent which id to cite.
    blob = str(out)
    assert "g1" in blob and "cite" in blob.lower()


@pytest.mark.asyncio
async def test_hook_ignores_non_graph_tools() -> None:
    led = ProvenanceLedger()
    hook = make_provenance_hook(led)
    out = await hook(
        {"tool_name": "Read", "tool_input": {"file_path": "/x"}, "tool_response": "data"},
        "tool-use-2",
        None,
    )
    assert led.entries == []
    assert out == {}


@pytest.mark.asyncio
async def test_hook_reads_tool_output_fallback_key() -> None:
    led = ProvenanceLedger()
    hook = make_provenance_hook(led)
    await hook(
        {"tool_name": "mcp__neo4j__get_neo4j_schema", "tool_input": {}, "tool_output": "schema"},
        "tool-use-3",
        None,
    )
    assert "schema" in led.entries[0]["response_excerpt"]
