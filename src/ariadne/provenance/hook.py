"""The PostToolUse provenance hook.

Fires after every tool call. For evidence-store calls (``mcp__neo4j__*`` graph or
``mcp__postgres__*`` relational) it records the call in the ledger and returns an
``additionalContext`` string telling the agent the ``[cite:gN]`` id to attach to
facts derived from that result. The ``g`` id is source-agnostic ("grounding");
the ledger keeps the tool name, so the source stays recoverable. The matcher is
transport-agnostic — this works against the external stdio MCP servers.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, cast

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

if TYPE_CHECKING:
    from ariadne.provenance.ledger import ProvenanceLedger

# Evidence-store tool families whose calls are recorded for citation.
EVIDENCE_TOOL_PREFIXES = ("mcp__neo4j__", "mcp__postgres__", "mcp__ariadne__")


def _source_label(tool: str) -> str:
    if tool.startswith("mcp__neo4j__"):
        return "graph"
    if tool.startswith("mcp__postgres__"):
        return "relational"
    if tool.startswith("mcp__ariadne__"):
        return "text"
    return "evidence"


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
        if not tool.startswith(EVIDENCE_TOOL_PREFIXES):
            return cast("SyncHookJSONOutput", {})
        response = data.get("tool_response", "")
        cite_id = ledger.record(tool, data.get("tool_input", {}), response)
        return cast(
            "SyncHookJSONOutput",
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": (
                        f"Provenance: this {_source_label(tool)} result is recorded as "
                        f"{cite_id}. Cite every fact you derive from it as [cite:{cite_id}]."
                    ),
                }
            },
        )

    return provenance_hook
