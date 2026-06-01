"""Ariadne CLI — `ariadne workup <entity>` runs the live agent loop.

Assembles ClaudeAgentOptions (read-only Neo4j MCP server + PostToolUse provenance
hook + entity-workup skill), runs the agent, validates citations, and persists the
note + ledger + citation report.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    HookMatcher,
    ResultMessage,
    TextBlock,
    query,
)

from ariadne.graph.neo4j_server import GRAPH_TOOLS, neo4j_stdio_config
from ariadne.provenance.citations import validate_citations
from ariadne.provenance.hook import make_provenance_hook
from ariadne.provenance.ledger import ProvenanceLedger
from ariadne.report.note import write_outputs

_SYSTEM_PROMPT = (
    "You are Ariadne, a sensemaking harness for intelligence analysts. Use only "
    "the read-only graph tools to gather evidence, and follow the entity-workup "
    "skill. Cite every fact as [cite:gN]. Output only the finished analytic note."
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ariadne")
    sub = parser.add_subparsers(dest="command", required=True)
    wk = sub.add_parser("workup", help="Work up a target entity or org node")
    wk.add_argument("entity", help="Target entity or organizational node")
    wk.add_argument("--graph", default="neo4j", choices=["neo4j"], help="Graph backend")
    wk.add_argument("--out", default="./workups", help="Output directory root")
    return parser.parse_args(argv)


def build_options(*, ledger: ProvenanceLedger, env: dict[str, str]) -> ClaudeAgentOptions:
    hook = make_provenance_hook(ledger)
    return ClaudeAgentOptions(
        mcp_servers={"neo4j": neo4j_stdio_config(env)},
        allowed_tools=list(GRAPH_TOOLS),
        system_prompt=_SYSTEM_PROMPT,
        permission_mode="default",
        setting_sources=["project"],  # discover .claude/skills/entity-workup
        hooks={"PostToolUse": [HookMatcher(matcher="mcp__neo4j__.*", hooks=[hook])]},
    )


async def run_workup(entity: str, out_root: str, env: dict[str, str]) -> int:
    ledger = ProvenanceLedger()
    options = build_options(ledger=ledger, env=env)
    prompt = f"Run entity workup on: {entity}"

    note_parts: list[str] = []
    result_text: str | None = None
    had_error: bool = False
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            note_parts.extend(
                block.text for block in message.content if isinstance(block, TextBlock)
            )
        elif isinstance(message, ResultMessage):
            result_text = message.result
            had_error = bool(getattr(message, "is_error", False))

    note = (result_text or "\n".join(note_parts)).strip()
    report = validate_citations(note, ledger)
    out_dir = Path(out_root) / _slug(entity)
    write_outputs(out_dir, entity=entity, note=note, ledger=ledger, report=report)

    print(f"Wrote {out_dir}/note.md ({len(ledger.entries)} graph calls cited).")
    if had_error:
        print("agent run reported an error", file=sys.stderr)
        return 1
    if not report.ok:
        print(f"Citation check FAILED — dangling: {report.dangling}", file=sys.stderr)
        return 1
    return 0


def _slug(entity: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in entity).strip("-").lower() or "entity"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "ANTHROPIC_API_KEY is not set — export it to run the live agent loop.",
            file=sys.stderr,
        )
        return 2
    return asyncio.run(run_workup(args.entity, args.out, dict(os.environ)))
