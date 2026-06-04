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
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    HookMatcher,
    ResultMessage,
    TextBlock,
    query,
)
from dotenv import find_dotenv, load_dotenv

import ariadne.datasets.enron  # side-effect: registers the enron adapter
import ariadne.datasets.synthetic  # noqa: F401  (registers the synthetic adapter)
from ariadne.datasets.base import DATASETS
from ariadne.evaluation.needle import FIXTURES, score_workup_dir
from ariadne.evaluation.reconcile import RECON_FIXTURES, score_reconciliation_dir
from ariadne.graph.neo4j_server import GRAPH_TOOLS, neo4j_stdio_config
from ariadne.observability import record_workup_metrics, setup_telemetry, workup_span
from ariadne.provenance.citations import validate_citations
from ariadne.provenance.governance import audit_read_only
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
    wk.add_argument(
        "--semantic",
        action="store_true",
        help="Enable hybrid full-text+semantic search over email bodies "
        "(needs the 'embed' extra + Postgres).",
    )
    wk.add_argument(
        "--entail",
        action="store_true",
        help="Check citation entailment (precision) with HHEM (needs the 'eval' extra).",
    )
    ev = sub.add_parser("eval", help="Score a workup dir against the planted-needle fixture")
    ev.add_argument("workup_dir", help="Workup output dir (note.md + provenance.jsonl)")
    ev.add_argument(
        "--fixture",
        choices=sorted(FIXTURES),
        default="halberd",
        help="Needle fixture: 'halberd' (single-store graph) or 'wren-tie' (cross-store)",
    )
    ev.add_argument(
        "--reconcile",
        choices=sorted(RECON_FIXTURES),
        default=None,
        help="Also score cross-store reconciliation (corroborations + conflicts).",
    )
    rb = sub.add_parser(
        "rubric", help="Score a workup's note against the ICD-203 rubric (LLM judge)"
    )
    rb.add_argument("workup_dir", help="Workup output dir (reads note.md)")
    rb.add_argument(
        "--min",
        type=float,
        default=None,
        help="Fail (exit 1) if the overall score is below this threshold (1-5). "
        "Default: informational only.",
    )
    ix = sub.add_parser("index", help="Load a dataset's records into the live stores")
    ix.add_argument(
        "--dataset",
        choices=sorted(DATASETS),
        default="synthetic",
        help="Dataset to index (default: synthetic).",
    )
    ix.add_argument(
        "--semantic",
        action="store_true",
        help="Also compute + store document embeddings (semantic leg; needs the 'embed' extra + pgvector).",
    )
    wk.add_argument(
        "--profile",
        default="default",
        help="Model profile from the curated allowlist (see `ariadne profiles`).",
    )
    pr = sub.add_parser("profiles", help="List or validate the available model profiles")
    pr.add_argument(
        "--validate",
        metavar="NAME",
        default=None,
        help="Run a real workup with NAME against the Halberd needle; PASS iff it grounds.",
    )
    pr.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        help="Wall-clock budget (seconds) for --validate (default 600).",
    )
    return parser.parse_args(argv)


def _run_eval(workup_dir: str, fixture_name: str = "halberd", reconcile: str | None = None) -> int:
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
    if reconcile is not None:
        rec = score_reconciliation_dir(workup_dir, RECON_FIXTURES[reconcile])
        print(
            f"Reconciliation [{rec.entity}/{reconcile}]: reconciliation={rec.reconciliation:.2f} "
            f"(corroboration={rec.corroboration:.2f} conflict={rec.conflict:.2f}) "
            f"{rec.handled}/{rec.total} cases"
        )
    return 0 if report.grounded else 1


def _run_rubric(workup_dir: str, minimum: float | None = None) -> int:
    """Score a workup's note against the ICD-203 rubric with the live Claude judge.

    Needs ANTHROPIC_API_KEY + the 'rubric' extra. Informational by default; with
    ``--min`` it becomes a CI-gateable pass/fail on the overall score.
    """
    from ariadne.evaluation.judge import ClaudeAnalyticJudge
    from ariadne.evaluation.rubric import score_note_dir

    report = score_note_dir(workup_dir, ClaudeAnalyticJudge())
    print(f"Rubric (ICD-203) overall={report.overall:.2f}/5")
    for s in report.dimensions:
        print(f"  {s.key:<14} {s.score}/5  {s.rationale}")
    if minimum is not None and report.overall < minimum:
        print(f"Rubric FAILED — overall {report.overall:.2f} < {minimum:.2f}", file=sys.stderr)
        return 1
    return 0


async def _run_under_budget(coro, budget: float) -> int | None:
    """Return the workup's exit code, or None if it exceeded the wall-clock budget."""
    try:
        return await asyncio.wait_for(coro, timeout=budget)
    except TimeoutError:
        return None


def _validate_profile(
    name: str,
    *,
    env: dict[str, str],
    timeout: float = 600.0,
    runner=None,
    scorer=None,
) -> int:
    """Run a real workup with `name` against the Halberd needle under a budget; PASS iff grounded."""
    import tempfile
    from pathlib import Path

    from ariadne.evaluation.needle import FIXTURES, score_workup_dir
    from ariadne.profiles import load_profiles, resolve_profile

    resolve_profile(name, load_profiles(env))  # clear error if the name is not in the allowlist
    runner = runner or run_workup
    scorer = scorer or (lambda d: score_workup_dir(d, FIXTURES["halberd"]))
    out_root = tempfile.mkdtemp(prefix="ariadne-validate-")
    rc = asyncio.run(
        _run_under_budget(
            runner("Halberd", out_root, env, dataset="synthetic", profile=name), budget=timeout
        )
    )
    if rc is None:
        print(
            f"Profile {name!r}: FAIL — workup exceeded the {timeout:.0f}s budget "
            f"(throughput-bound; not viable on this host).",
            file=sys.stderr,
        )
        return 1
    report = scorer(str(Path(out_root) / _slug("Halberd")))
    status = "PASS" if report.grounded else "FAIL"
    print(
        f"Profile {name!r}: {status} — grounded={report.grounded} "
        f"recall={report.recall:.2f} trajectory={report.trajectory:.2f}"
    )
    return 0 if report.grounded else 1


def _run_profiles(env: dict[str, str]) -> int:
    """List the curated model profiles this deployment offers."""
    from ariadne.profiles import load_profiles

    for name, p in sorted(load_profiles(env).items()):
        model = p.model or "(deployment default)"
        print(f"{name:<14} egress={p.egress:<9} model={model}")
        if p.description:
            print(f"{'':<14} {p.description}")
    return 0


def _run_index(dataset: str, env: dict[str, str], semantic: bool = False) -> int:
    """Load a dataset's canonical records into the live stores (graph + documents)."""
    import psycopg
    from neo4j import GraphDatabase

    from ariadne.datasets.base import get_adapter
    from ariadne.datasets.load import load_documents, load_graph

    records = list(get_adapter(dataset).load())
    with GraphDatabase.driver(
        env.get("NEO4J_URI", "bolt://localhost:7687"),
        auth=(env.get("NEO4J_USERNAME", "neo4j"), env.get("NEO4J_PASSWORD", "password")),
    ) as driver:
        n_graph = load_graph(records, driver)
    embedder = None
    if semantic:
        from ariadne.unstructured.embed import SentenceTransformerEmbedder

        embedder = SentenceTransformerEmbedder()
    with psycopg.connect(
        env.get("DATABASE_URI", "postgresql://ariadne:ariadne@localhost:5432/intel"),
        autocommit=True,
    ) as conn:
        n_docs, n_attrs = load_documents(records, conn, embedder=embedder)
    print(
        f"Indexed {dataset}: {n_graph} graph statements, {n_docs} documents, {n_attrs} attributes."
    )
    return 0


def build_options(
    *,
    ledger: ProvenanceLedger,
    env: dict[str, str],
    with_sql: bool = False,
    with_semantic: bool = False,
    model: str | None = None,
    max_turns: int | None = None,
    max_thinking_tokens: int | None = None,
) -> ClaudeAgentOptions:
    hook = make_provenance_hook(ledger)
    mcp_servers: dict[str, McpServerConfig] = {"neo4j": neo4j_stdio_config(env)}
    allowed_tools = list(GRAPH_TOOLS)
    matchers = [HookMatcher(matcher="mcp__neo4j__.*", hooks=[hook])]
    if with_sql:
        mcp_servers["postgres"] = postgres_stdio_config(env)
        allowed_tools += list(RELATIONAL_TOOLS)
        matchers.append(HookMatcher(matcher="mcp__postgres__.*", hooks=[hook]))
    if with_semantic:
        from ariadne.unstructured.embed import SentenceTransformerEmbedder
        from ariadne.unstructured.search_tool import ARIADNE_TOOLS, make_ariadne_server

        embedder = SentenceTransformerEmbedder()
        mcp_servers["ariadne"] = make_ariadne_server(env, embedder)
        allowed_tools += list(ARIADNE_TOOLS)
        matchers.append(HookMatcher(matcher="mcp__ariadne__.*", hooks=[hook]))
    # Envelope/model are optional: omit unset fields so the SDK default applies.
    extra: dict[str, Any] = {}
    if model is not None:
        extra["model"] = model
    if max_turns is not None:
        extra["max_turns"] = max_turns
    if max_thinking_tokens is not None:
        extra["max_thinking_tokens"] = max_thinking_tokens
    return ClaudeAgentOptions(
        mcp_servers=mcp_servers,
        allowed_tools=allowed_tools,
        system_prompt=_SYSTEM_PROMPT,
        permission_mode="default",
        skills=["entity-workup"],  # SDK auto-allows Skill tool and sets setting_sources
        hooks={"PostToolUse": matchers},
        **extra,
    )


async def run_workup(
    entity: str,
    out_root: str,
    env: dict[str, str],
    *,
    with_sql: bool = False,
    with_semantic: bool = False,
    with_entail: bool = False,
    dataset: str = "synthetic",
    profile: str = "default",
) -> int:
    from ariadne.datasets.base import get_adapter
    from ariadne.profiles import load_profiles, resolve_profile

    get_adapter(dataset)  # raises KeyError on unknown; synthetic uses the seeded graph
    prof = resolve_profile(profile, load_profiles(env))
    ledger = ProvenanceLedger()
    options = build_options(
        ledger=ledger,
        env=env,
        with_sql=with_sql,
        with_semantic=with_semantic,
        model=prof.model,
        max_turns=prof.envelope.max_turns,
        max_thinking_tokens=prof.envelope.max_thinking_tokens,
    )
    verifier = None
    if with_entail:
        from ariadne.provenance.entailment import HHEMVerifier

        verifier = HHEMVerifier()
    prompt = f"Run entity workup on: {entity}"

    note_parts: list[str] = []
    result_text: str | None = None
    had_error: bool = False
    with workup_span(entity, dataset, semantic=with_semantic, sql=with_sql):
        started = time.monotonic()
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                note_parts.extend(
                    block.text for block in message.content if isinstance(block, TextBlock)
                )
            elif isinstance(message, ResultMessage):
                result_text = message.result
                had_error = bool(getattr(message, "is_error", False))
        elapsed = time.monotonic() - started
        note = (result_text or "\n".join(note_parts)).strip()
        report = validate_citations(note, ledger, verifier=verifier)
        tradecraft = lint_estimative_language(note)
        governance = audit_read_only(ledger.entries)
        record_workup_metrics(
            entity=entity,
            dataset=dataset,
            duration_s=elapsed,
            report=report,
            tradecraft=tradecraft,
            led=ledger,
            governance=governance,
            profile=prof,
        )
        out_dir = Path(out_root) / _slug(entity)
        write_outputs(
            out_dir,
            entity=entity,
            note=note,
            ledger=ledger,
            report=report,
            tradecraft=tradecraft,
            governance=governance,
            profile=prof,
        )

    print(f"Wrote {out_dir}/note.md ({len(ledger.entries)} graph calls cited) in {elapsed:.1f}s.")
    if tradecraft.nonstandard_terms:
        print(
            "Tradecraft (advisory): non-standard estimative terms "
            f"{sorted(set(tradecraft.nonstandard_terms))} — prefer ICD-203 bands.",
            file=sys.stderr,
        )
    if not governance.ok:
        verbs = sorted({w["verb"] for w in governance.write_attempts})
        print(
            f"GOVERNANCE: read-only contract violated — write verbs in the ledger {verbs}. "
            "The analytic loop must not mutate the evidence stores.",
            file=sys.stderr,
        )
    if had_error:
        print("agent run reported an error", file=sys.stderr)
        return 1
    if not report.ok:
        print(
            f"Citation check FAILED — dangling: {report.dangling} · "
            f"uncited claims: {len(report.uncited)} · "
            f"unsupported claims: {len(report.unsupported)}",
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
    setup_telemetry()
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "eval":
        return _run_eval(args.workup_dir, args.fixture, reconcile=args.reconcile)
    if args.command == "index":
        return _run_index(args.dataset, dict(os.environ), semantic=args.semantic)
    if args.command == "profiles":
        if args.validate:
            return _validate_profile(args.validate, env=dict(os.environ), timeout=args.timeout)
        return _run_profiles(dict(os.environ))
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "ANTHROPIC_API_KEY is not set — export it to run the live agent loop.",
            file=sys.stderr,
        )
        return 2
    if args.command == "rubric":
        return _run_rubric(args.workup_dir, args.min)
    return asyncio.run(
        run_workup(
            args.entity,
            args.out,
            dict(os.environ),
            with_sql=args.sql,
            with_semantic=args.semantic,
            with_entail=args.entail,
            dataset=args.dataset,
            profile=args.profile,
        )
    )
