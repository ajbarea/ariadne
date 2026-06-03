from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from ariadne.provenance.hook import make_provenance_hook
from ariadne.provenance.ledger import ProvenanceLedger

if TYPE_CHECKING:
    from claude_agent_sdk.types import HookContext, PostToolUseHookInput

_CTX = cast("HookContext", {"signal": None})


@pytest.mark.asyncio
async def test_hook_records_graph_calls_and_returns_cite_context() -> None:
    led = ProvenanceLedger()
    hook = make_provenance_hook(led)
    out = await hook(
        cast(
            "PostToolUseHookInput",
            {
                "tool_name": "mcp__neo4j__read_neo4j_cypher",
                "tool_input": {"query": "MATCH (n) RETURN n"},
                "tool_response": "rows...",
            },
        ),
        "tool-use-1",
        _CTX,
    )
    assert led.has("g1")
    # The hook tells the agent which id to cite.
    blob = str(out)
    assert "g1" in blob and "cite" in blob.lower()


@pytest.mark.asyncio
async def test_hook_records_relational_calls_too() -> None:
    # Heterogeneous retrieval: SQL evidence is cited the same way as graph evidence.
    led = ProvenanceLedger()
    hook = make_provenance_hook(led)
    out = await hook(
        cast(
            "PostToolUseHookInput",
            {
                "tool_name": "mcp__postgres__execute_sql",
                "tool_input": {"sql": "SELECT * FROM personnel"},
                "tool_response": "rows...",
            },
        ),
        "tool-use-sql",
        _CTX,
    )
    assert led.has("g1")
    assert "g1" in str(out) and "cite" in str(out).lower()


@pytest.mark.asyncio
async def test_hook_ignores_non_evidence_tools() -> None:
    led = ProvenanceLedger()
    hook = make_provenance_hook(led)
    out = await hook(
        cast(
            "PostToolUseHookInput",
            {"tool_name": "Read", "tool_input": {"file_path": "/x"}, "tool_response": "data"},
        ),
        "tool-use-2",
        _CTX,
    )
    assert led.entries == []
    assert out == {}


@pytest.mark.asyncio
async def test_hook_handles_missing_response() -> None:
    led = ProvenanceLedger()
    hook = make_provenance_hook(led)
    await hook(
        cast(
            "PostToolUseHookInput",
            {"tool_name": "mcp__neo4j__get_neo4j_schema", "tool_input": {}},
        ),
        "tool-use-3",
        _CTX,
    )
    assert led.entries[0]["response_excerpt"] == ""
