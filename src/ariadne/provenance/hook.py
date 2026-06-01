"""The PostToolUse provenance hook.

Fires after every tool call. For graph calls (``mcp__neo4j__*``) it records the
call in the ledger and returns an ``additionalContext`` string telling the agent
the ``[cite:gN]`` id to attach to facts derived from that result. The matcher is
transport-agnostic — this works against the external stdio Neo4j MCP server.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from ariadne.provenance.ledger import ProvenanceLedger  # noqa: TC001

GRAPH_TOOL_PREFIX = "mcp__neo4j__"

Hook = Callable[[dict[str, Any], str | None, Any], Awaitable[dict[str, Any]]]


def make_provenance_hook(ledger: ProvenanceLedger) -> Hook:
    """Build a PostToolUse callback bound to ``ledger``."""

    async def provenance_hook(
        input_data: dict[str, Any],
        _tool_use_id: str | None,
        _context: Any,
    ) -> dict[str, Any]:
        tool = input_data.get("tool_name", "")
        if not tool.startswith(GRAPH_TOOL_PREFIX):
            return {}
        response = input_data.get("tool_response", input_data.get("tool_output", ""))
        cite_id = ledger.record(tool, input_data.get("tool_input", {}), response)
        return {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": (
                    f"Provenance: this graph result is recorded as {cite_id}. "
                    f"Cite every fact you derive from it as [cite:{cite_id}]."
                ),
            }
        }

    return provenance_hook
