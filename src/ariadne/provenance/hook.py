"""The PostToolUse provenance hook.

Fires after every tool call. For graph calls (``mcp__neo4j__*``) it records the
call in the ledger and returns an ``additionalContext`` string telling the agent
the ``[cite:gN]`` id to attach to facts derived from that result. The matcher is
transport-agnostic — this works against the external stdio Neo4j MCP server.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, cast

from claude_agent_sdk.types import (
    AsyncHookJSONOutput,
    HookContext,
    NotificationHookInput,
    PermissionRequestHookInput,
    PostToolUseFailureHookInput,
    PostToolUseHookInput,
    PreCompactHookInput,
    PreToolUseHookInput,
    StopHookInput,
    SubagentStartHookInput,
    SubagentStopHookInput,
    SyncHookJSONOutput,
    UserPromptSubmitHookInput,
)

from ariadne.provenance.ledger import ProvenanceLedger  # noqa: TC001

GRAPH_TOOL_PREFIX = "mcp__neo4j__"

_HookInput = (
    PreToolUseHookInput
    | PostToolUseHookInput
    | PostToolUseFailureHookInput
    | UserPromptSubmitHookInput
    | StopHookInput
    | SubagentStopHookInput
    | PreCompactHookInput
    | NotificationHookInput
    | SubagentStartHookInput
    | PermissionRequestHookInput
)

Hook = Callable[
    [_HookInput, str | None, HookContext], Awaitable[AsyncHookJSONOutput | SyncHookJSONOutput]
]


def make_provenance_hook(ledger: ProvenanceLedger) -> Hook:
    """Build a PostToolUse callback bound to ``ledger``."""

    async def provenance_hook(
        input_data: _HookInput,
        _tool_use_id: str | None,
        _context: HookContext,
    ) -> AsyncHookJSONOutput | SyncHookJSONOutput:
        # input_data is a TypedDict; cast to dict for generic key access across variants
        data: dict[str, Any] = cast("dict[str, Any]", input_data)
        tool: str = data.get("tool_name", "")
        if not tool.startswith(GRAPH_TOOL_PREFIX):
            return cast("SyncHookJSONOutput", {})
        response = data.get("tool_response", data.get("tool_output", ""))
        cite_id = ledger.record(tool, data.get("tool_input", {}), response)
        return cast(
            "SyncHookJSONOutput",
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": (
                        f"Provenance: this graph result is recorded as {cite_id}. "
                        f"Cite every fact you derive from it as [cite:{cite_id}]."
                    ),
                }
            },
        )

    return provenance_hook
