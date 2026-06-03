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
from typing import TYPE_CHECKING

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    HookMatcher,
    ResultMessage,
    TextBlock,
    query,
)
from dotenv import find_dotenv, load_dotenv

import ariadne.datasets.synthetic  # noqa: F401  (registers the synthetic adapter)
from ariadne.datasets.base import DATASETS
from ariadne.evaluation.needle import FIXTURES, score_workup_dir
from ariadne.graph.neo4j_server import GRAPH_TOOLS, neo4j_stdio_config
from ariadne.provenance.citations import validate_citations
from ariadne.provenance.hook import make_provenance_hook
from ariadne.provenance.ledger import ProvenanceLedger
from ariadne.provenance.tradecraft import lint_estimative_language
from ariadne.relational.postgres_server import RELATIONAL_TOOLS, postgres_stdio_config
from ariadne.report.note import write_outputs

if TYPE_CHECKING:
    from claude_agent_sdk.types import McpServerConfig

_SYSTEM_PROMPT = (
    "You are Ariadne, a sensemaking harness for intelligence analysts. Use the "
    "available read-only evidence tools — the graph store and, when present, the "
    "relational store — to gather evidence, and follow the entity-workup skill. "
    "Cite every fact as [cite:gN]. Output only the finished analytic note."
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ariadne")
    sub = parser.add_subparsers(dest="command", required=True)
    wk = sub.add_parser("workup", help="Work up a target entity or org node")
    wk.add_argument("entity", help="Target entity or organizational node")
    wk.add_argument("--graph", default="neo4j", choices=["neo4j"], help="Graph backend")
    wk.add_argument("--out", default="./workups", help="Output directory root")
    wk.add_argument(
        "--sql",
        action="store_true",
        help="Also query the relational store (heterogeneous retrieval; needs Postgres)",
    )
    wk.add_argument(
        "--dataset",
        choices=sorted(DATASETS),
        default="synthetic",
        help="Which dataset to work up (default: synthetic).",
    )
    ev = sub.add_parser("eval", help="Score a workup dir against the planted-needle fixture")
    ev.add_argument("workup_dir", help="Workup output dir (note.md + provenance.jsonl)")
    ev.add_argument(
        "--fixture",
        choices=sorted(FIXTURES),
        default="halberd",
        help="Needle fixture: 'halberd' (single-store graph) or 'wren-tie' (cross-store)",
    )
    return parser.parse_args(argv)


def _run_eval(workup_dir: str, fixture_name: str = "halberd") -> int:
    """Score an existing workup against a planted-needle fixture (no API key needed)."""
    report = score_workup_dir(workup_dir, FIXTURES[fixture_name])
    line = (
        f"Eval [{report.entity}/{fixture_name}]: grounded={report.grounded} "
        f"recall={report.recall:.2f} trajectory={report.trajectory:.2f} "
        f"pivot_burden={report.pivot_burden:.2f} queries={report.queries_run}"
    )
    if report.supporting_fact_f1 is not None:
        line += (
            f" sf_f1={report.supporting_fact_f1:.2f} "
            f"(p={report.supporting_fact_precision:.2f} r={report.supporting_fact_recall:.2f})"
        )
    print(line)
    return 0 if report.grounded else 1


def build_options(
    *, ledger: ProvenanceLedger, env: dict[str, str], with_sql: bool = False
) -> ClaudeAgentOptions:
    hook = make_provenance_hook(ledger)
    mcp_servers: dict[str, McpServerConfig] = {"neo4j": neo4j_stdio_config(env)}
    allowed_tools = list(GRAPH_TOOLS)
    matchers = [HookMatcher(matcher="mcp__neo4j__.*", hooks=[hook])]
    if with_sql:
        mcp_servers["postgres"] = postgres_stdio_config(env)
        allowed_tools += list(RELATIONAL_TOOLS)
        matchers.append(HookMatcher(matcher="mcp__postgres__.*", hooks=[hook]))
    return ClaudeAgentOptions(
        mcp_servers=mcp_servers,
        allowed_tools=allowed_tools,
        system_prompt=_SYSTEM_PROMPT,
        permission_mode="default",
        skills=["entity-workup"],  # SDK auto-allows Skill tool and sets setting_sources
        hooks={"PostToolUse": matchers},
    )


async def run_workup(
    entity: str,
    out_root: str,
    env: dict[str, str],
    *,
    with_sql: bool = False,
    dataset: str = "synthetic",
) -> int:
    from ariadne.datasets.base import get_adapter

    get_adapter(dataset)  # raises KeyError on unknown; synthetic uses the seeded graph
    ledger = ProvenanceLedger()
    options = build_options(ledger=ledger, env=env, with_sql=with_sql)
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
    tradecraft = lint_estimative_language(note)
    out_dir = Path(out_root) / _slug(entity)
    write_outputs(
        out_dir, entity=entity, note=note, ledger=ledger, report=report, tradecraft=tradecraft
    )

    print(f"Wrote {out_dir}/note.md ({len(ledger.entries)} graph calls cited).")
    if tradecraft.nonstandard_terms:
        print(
            "Tradecraft (advisory): non-standard estimative terms "
            f"{sorted(set(tradecraft.nonstandard_terms))} — prefer ICD-203 bands.",
            file=sys.stderr,
        )
    if had_error:
        print("agent run reported an error", file=sys.stderr)
        return 1
    if not report.ok:
        print(
            f"Citation check FAILED — dangling: {report.dangling} · "
            f"uncited claims: {len(report.uncited)}",
            file=sys.stderr,
        )
        return 1
    return 0


def _slug(entity: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in entity).strip("-").lower() or "entity"


def main(argv: list[str] | None = None) -> int:
    # Load a local .env (cp .env.example .env) from the working dir, without
    # clobbering already-exported vars. usecwd=True searches up from where the
    # user runs the command (not from this installed module's location).
    load_dotenv(find_dotenv(usecwd=True), override=False)
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "eval":
        return _run_eval(args.workup_dir, args.fixture)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "ANTHROPIC_API_KEY is not set — export it to run the live agent loop.",
            file=sys.stderr,
        )
        return 2
    return asyncio.run(
        run_workup(args.entity, args.out, dict(os.environ), with_sql=args.sql, dataset=args.dataset)
    )
