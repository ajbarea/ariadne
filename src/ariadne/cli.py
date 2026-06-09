"""Ariadne CLI — `ariadne workup <entity>` runs the live agent loop.

Assembles ClaudeAgentOptions (read-only Neo4j MCP server + PostToolUse provenance
hook + entity-workup skill), runs the agent, validates citations, and persists the
note + ledger + citation report.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import traceback
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
import ariadne.datasets.lahman
import ariadne.datasets.synthetic
import ariadne.datasets.worldspeech  # noqa: F401  (registers the worldspeech adapter)
from ariadne.datasets.base import DATASETS
from ariadne.datasets.mapping_source import discover_and_register
from ariadne.evaluation.needle import FIXTURES, score_workup_dir, write_eval_json
from ariadne.evaluation.reconcile import RECON_FIXTURES, score_reconciliation_dir
from ariadne.graph.neo4j_server import GRAPH_TOOLS, neo4j_stdio_config
from ariadne.observability import (
    eval_span,
    record_eval_metrics,
    record_reconciliation_metrics,
    record_workup_metrics,
    setup_telemetry,
    workup_span,
)
from ariadne.preflight import workup_preflight
from ariadne.provenance.citations import citation_coverage, validate_citations
from ariadne.provenance.governance import audit_read_only
from ariadne.provenance.hook import make_provenance_hook
from ariadne.provenance.ledger import ProvenanceLedger
from ariadne.provenance.repair import repair_citations_loop
from ariadne.provenance.skills import skill_invocations
from ariadne.provenance.tradecraft import lint_estimative_language
from ariadne.relational.postgres_server import RELATIONAL_TOOLS, postgres_stdio_config
from ariadne.report.note import write_outputs
from ariadne.runs import (
    build_workup_manifest,
    current_trace_hex,
    merge_scores,
    run_dir,
    scores_from_reports,
    slug,
    update_latest,
    write_manifest,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from claude_agent_sdk.types import McpServerConfig

    from ariadne.provenance.governance import GovernanceReport

_SYSTEM_PROMPT = (
    "You are Ariadne, a sensemaking harness for intelligence analysts. Use the "
    "available read-only evidence tools — the graph store and, when present, the "
    "relational store — to gather evidence, and follow the entity-workup skill. "
    "Cite every fact as [cite:gN]. Output only the finished analytic note."
)

_REPAIR_SYSTEM_PROMPT = (
    "You are a meticulous intelligence-analysis citation editor. You attach existing "
    "provenance citations to under-cited claims and never fabricate evidence or ids. "
    "Output only the corrected Markdown note, with no preamble."
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ariadne")
    sub = parser.add_subparsers(dest="command", required=True)
    wk = sub.add_parser("workup", help="Work up a target entity or org node")
    wk.add_argument("entity", help="Target entity or organizational node")
    wk.add_argument("--graph", default="neo4j", choices=["neo4j"], help="Graph backend")
    wk.add_argument(
        "--out", default="runs", help="Run-output root: runs/<dataset>/<entity>/<run-id>/"
    )
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
    wk.add_argument(
        "--strict",
        action="store_true",
        help="Fail (exit 3) if the agent violated the read-only contract "
        "(attempted a write to the evidence stores). Default: advisory only.",
    )
    wk.add_argument(
        "--repair",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Post-hoc P-Cite pass: attach ledger cites to any uncited synthesis "
        "claims the recall gate finds, then re-check (bounded). --no-repair measures "
        "the raw single-pass draft. Default: on.",
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
        help="Run a real workup with NAME against each dataset's needle; PASS iff it grounds.",
    )
    pr.add_argument(
        "--dataset",
        choices=sorted(DATASETS),
        default=None,
        help="Restrict --validate to one dataset (default: all registered cases).",
    )
    pr.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        help="Wall-clock budget (seconds) per dataset for --validate (default 600).",
    )
    pr.add_argument(
        "--attempts",
        type=int,
        default=3,
        help="Validation tries per dataset; PASS if any grounds (default 3, for run variance).",
    )
    gov = sub.add_parser(
        "governance", help="Re-audit a persisted workup for read-only contract violations"
    )
    gov.add_argument("workup_dir", help="Workup output dir (reads provenance.jsonl)")
    rp = sub.add_parser(
        "report", help="Render a self-contained interactive report.html for a workup dir"
    )
    rp.add_argument("workup_dir", help="Workup output dir (reads note.md + the JSON artifacts)")
    mp = sub.add_parser(
        "map", help="Introspect a Postgres store and propose a draft mapping.toml (ADR-0020)"
    )
    mp.add_argument("--name", default="user_postgres", help="Dataset name for the [dataset] header")
    mp.add_argument(
        "--dsn",
        default=None,
        help="Source connection string; prefer $ARIADNE_SOURCE_DSN (argv is world-readable)",
    )
    mp.add_argument(
        "--dsn-env",
        default="ARIADNE_SOURCE_DSN",
        help="Env var holding the source DSN (default: ARIADNE_SOURCE_DSN)",
    )
    mp.add_argument("--schema", default="public", help="Schema to introspect (default: public)")
    mp.add_argument(
        "--out", default="mapping.toml", help="Draft mapping path (default: mapping.toml)"
    )
    mp.add_argument(
        "--llm",
        action="store_true",
        help="Propose with the Claude schema mapper instead of the deterministic baseline "
        "(needs the 'adaptive' extra + ANTHROPIC_API_KEY).",
    )
    mp.add_argument(
        "--ontology",
        default=None,
        help="Map into a user-declared ontology.toml (closed entity/relationship vocabulary): "
        "LLM-guided with --llm, validation-only without (ADR-0027).",
    )

    ds = sub.add_parser(
        "distil",
        help="Distil an eval-certified workup into a draft analytic skill (B2, ADR-0029)",
    )
    ds.add_argument("run_dir", help="A workup run dir (must carry an eval.json with grounded=true)")
    ds.add_argument(
        "--name", default=None, help="Skill slug (default: entity-workup-<dataset>; --llm proposes)"
    )
    ds.add_argument(
        "--out",
        default="skills-proposed",
        help="Where to write the draft (default: skills-proposed)",
    )
    ds.add_argument(
        "--llm",
        action="store_true",
        help="Generalize the trajectory into a transferable skill with the Claude distiller "
        "(needs the 'adaptive' extra + ANTHROPIC_API_KEY); else a deterministic record.",
    )
    ds.add_argument(
        "--into",
        default=None,
        metavar="SKILL_DIR",
        help="Deepen this existing skill from the run instead of creating one (LLM-only, "
        "ADR-0032); ratify after `ariadne compare` shows a net gain.",
    )

    rf = sub.add_parser(
        "reflect",
        help="Reflect on an eval-scored workup's shortfalls + propose refinements (B3, ADR-0030)",
    )
    rf.add_argument("run_dir", help="A workup run dir (must carry an eval.json)")
    rf.add_argument(
        "--out", default=None, help="Where to write reflection.{md,json} (default: the run dir)"
    )
    rf.add_argument(
        "--llm",
        action="store_true",
        help="Run the Claude reflexion (post-mortem + proposed refinements) over the findings "
        "(needs the 'adaptive' extra + ANTHROPIC_API_KEY); else a deterministic diagnosis.",
    )

    cmp = sub.add_parser(
        "compare",
        help="Net a candidate's effect vs a baseline on the same instance (ratify step, ADR-0031)",
    )
    cmp.add_argument(
        "--baseline", nargs="+", required=True, metavar="RUN", help="Baseline run dir(s)"
    )
    cmp.add_argument(
        "--candidate", nargs="+", required=True, metavar="RUN", help="Candidate run dir(s)"
    )
    cmp.add_argument(
        "--out", default=None, help="Also write the structured comparison.json to this path"
    )

    rt = sub.add_parser(
        "ratify",
        help="Produce paired with/without-skill runs + net their effect, auto-freeze (ADR-0034)",
    )
    rt.add_argument("candidate_skill", help="A proposed skill dir (e.g. skills-proposed/<name>)")
    rt.add_argument("--entity", required=True, help="The entity / org node to work up each trial")
    rt.add_argument(
        "--dataset", default="synthetic", help="Dataset to work up (default: synthetic)"
    )
    rt.add_argument(
        "--fixture",
        default="halberd",
        help="Planted-needle fixture to score each run (default: halberd)",
    )
    rt.add_argument(
        "-n",
        "--trials",
        type=int,
        default=3,
        help="Trials per arm (default: 3; < 3 is caveated as noisy)",
    )
    rt.add_argument("--out", default="runs", help="Where the produced runs land (default: runs/)")
    rt.add_argument(
        "--base-skill",
        action="append",
        default=None,
        dest="base_skill",
        metavar="SKILL_DIR",
        help="An always-on base skill dir (repeatable; default: .claude/skills/entity-workup)",
    )
    rt.add_argument("--sql", action="store_true", help="Give each workup the relational store")
    rt.add_argument("--semantic", action="store_true", help="Give each workup the semantic leg")
    rt.add_argument(
        "--apply",
        action="store_true",
        help="Freeze the skill into .claude/skills/ on a clean ratify (else propose-only)",
    )
    return parser.parse_args(argv)


def _missing_workup(workup_dir: str, *required: str) -> str | None:
    """An actionable message if the dir or a required artifact is absent, else ``None``.

    Serves both the human reading the terminal and the agent driving the MCP: state what is
    wrong and how to fix it, rather than leaking a FileNotFoundError traceback.
    """
    directory = Path(workup_dir)
    if not directory.is_dir():
        return (
            f"No run directory at '{workup_dir}'. Point at a workup output dir such as "
            "runs/<dataset>/<slug>/latest, or run `ariadne workup <entity>` first."
        )
    missing = [name for name in required if not (directory / name).is_file()]
    if missing:
        return (
            f"'{workup_dir}' is not a finished workup (missing {', '.join(missing)}). "
            "Run `ariadne workup <entity>` first, or point at runs/<dataset>/<slug>/latest."
        )
    return None


def _run_report(workup_dir: str) -> int:
    """Render the offline interactive report.html from a persisted workup."""
    msg = _missing_workup(workup_dir, "note.md")
    if msg:
        print(msg, file=sys.stderr)
        return 2
    from ariadne.report.html import write_report

    out = write_report(workup_dir)
    print(f"Wrote {out}")
    return 0


def _run_map(
    name: str,
    out: str,
    schema: str = "public",
    *,
    dsn: str | None = None,
    dsn_env: str = "ARIADNE_SOURCE_DSN",
    llm: bool = False,
    ontology: str | None = None,
) -> int:
    """Introspect a Postgres store and write a draft ``mapping.toml``.

    The read-only *propose* step of propose -> ratify -> freeze. The source DSN is
    read from ``$dsn_env`` (kept off argv); ``--dsn`` overrides. ``--llm`` proposes
    with the Claude schema mapper (ADR-0026) instead of the deterministic baseline;
    otherwise no API key is needed. ``--ontology`` constrains the mapping to a
    user-declared vocabulary (ADR-0027): LLM-guided with ``--llm``, validation-only
    otherwise. The draft carries a ``[dataset]`` header so, once ratified under
    ``$ARIADNE_MAPPINGS``, it applies via ``ariadne index --dataset <name>`` (ADR-0025).
    """
    import psycopg

    from ariadne.datasets.mapping_source import resolve_source_dsn
    from ariadne.mapping.propose import propose_and_write
    from ariadne.mapping.schema import DatasetHeader

    # Load the ontology before any connection or key check, so a bad path fails fast
    # and hermetically (mirrors the --llm key-guard below).
    ont = None
    if ontology is not None:
        ont_path = Path(ontology)
        if not ont_path.exists():
            print(f"Ontology file not found: {ontology}", file=sys.stderr)
            return 2
        from ariadne.mapping.ontology import load_ontology_toml

        ont = load_ontology_toml(ont_path.read_text(encoding="utf-8"))

    mapper = None
    if llm:
        # Key-guard before any source connection or anthropic import (mirrors the
        # workup key-guard): a missing key exits cleanly, nothing is written.
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print(
                "ANTHROPIC_API_KEY is not set — export it to use --llm (the Claude mapper).",
                file=sys.stderr,
            )
            return 2
        from ariadne.mapping.llm_mapper import ClaudeSchemaMapper

        mapper = ClaudeSchemaMapper(ontology=ont)
    dsn = dsn or resolve_source_dsn(dict(os.environ), dsn_env)
    header = DatasetHeader(name=name, dsn_env=dsn_env, schema=schema)
    with psycopg.connect(dsn) as conn:
        mapping, errors = propose_and_write(
            conn, out, schema=schema, mapper=mapper, header=header, ontology=ont
        )
    print(
        f"Proposed mapping -> {out}: {len(mapping.entities)} entit(ies), "
        f"{len(mapping.relationships)} relationship(s) from schema {schema!r} as dataset {name!r}."
    )
    if errors:
        print(f"{len(errors)} validation issue(s) to resolve before use:", file=sys.stderr)
        for e in errors:
            print(f"  ! {e}", file=sys.stderr)
        return 1
    print(
        f"Review/edit {out}, place it under $ARIADNE_MAPPINGS, set ${dsn_env}, "
        f"then: ariadne index --dataset {name}"
    )
    return 0


def _run_distil(
    run_dir: str,
    *,
    name: str | None = None,
    out: str = "skills-proposed",
    llm: bool = False,
    into: str | None = None,
) -> int:
    """Distil an eval-certified workup into a draft analytic skill (B2, ADR-0029/0032).

    The *propose* step of propose -> ratify -> freeze: only a run the eval harness scored
    ``grounded`` is a skill source (the external verifiable reward — the gate the loop may
    never edit). ``--llm`` generalizes the trajectory into transferable prose (the Trace2Skill
    move) behind a key-guard + the ``adaptive`` extra; otherwise a deterministic record.
    ``--into <skill-dir>`` *deepens* that existing skill from this run instead of creating one
    (LLM-only, ADR-0032). The draft lands under ``out/<name>/`` for review; ratify after
    ``ariadne compare`` shows a net gain.
    """
    from ariadne.learning.distil import (
        NotCertified,
        distil_deepen,
        distil_deterministic,
        distil_with_llm,
        write_skill,
    )
    from ariadne.learning.runs import load_run

    if into and not llm:
        print(
            "deepening (--into) requires --llm; the deterministic distiller can only create, "
            "not integrate (ADR-0032).",
            file=sys.stderr,
        )
        return 2

    distiller = None
    if llm:
        # Key-guard before load_run or any anthropic import (mirrors --map --llm): a missing
        # key exits cleanly, nothing is written.
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print(
                "ANTHROPIC_API_KEY is not set — export it to use --llm (the Claude distiller).",
                file=sys.stderr,
            )
            return 2
        from ariadne.learning.distil import ClaudeSkillDistiller

        distiller = ClaudeSkillDistiller()

    existing_skill_md = None
    if into:
        skill_md = Path(into) / "SKILL.md"
        if not skill_md.is_file():
            print(f"No SKILL.md under {into} to deepen.", file=sys.stderr)
            return 2
        existing_skill_md = skill_md.read_text(encoding="utf-8")

    run = load_run(run_dir)
    try:
        if existing_skill_md is not None and distiller is not None:
            skill = distil_deepen(
                run,
                existing_skill_md=existing_skill_md,
                call_llm=distiller.call_llm,
                name=name,
                model=distiller.model,
            )
        elif distiller is not None:
            skill = distil_with_llm(
                run, call_llm=distiller.call_llm, name=name, model=distiller.model
            )
        else:
            skill = distil_deterministic(run, name=name)
    except NotCertified as exc:
        print(f"Cannot distil {run_dir}: {exc}", file=sys.stderr)
        return 1

    out_dir = write_skill(out, skill)
    prereqs = ", ".join(skill.card.prerequisites)
    print(
        f"Proposed skill -> {out_dir}/ "
        f"({skill.card.granularity}, prerequisites: {prereqs}, distilled_by {skill.card.distilled_by})."
    )
    if into:
        print(
            f"Deepened `{skill.card.name}`. Ratify by measuring it: run a workup with the revised "
            f"skill vs the original, then `ariadne compare` — adopt only on a net gain (ADR-0031)."
        )
    else:
        print(
            f"Review/edit {out_dir}/SKILL.md, then ratify by moving it: "
            f"mv {out_dir} .claude/skills/{skill.card.name}"
        )
    return 0


def _run_reflect(run_dir: str, *, out: str | None = None, llm: bool = False) -> int:
    """Reflect on an eval-scored workup's shortfalls and propose refinements (B3, ADR-0030).

    Eval-triggered and gold-free: reads the run's own scores + artifacts, never the held-out
    gold. ``--llm`` runs the Claude reflexion (post-mortem + proposed refinements) over the
    findings behind a key-guard; otherwise a deterministic diagnosis. Propose-only — the
    reflection is written beside the run's artifacts for a human to ratify; nothing is applied.
    """
    from ariadne.learning.reflect import (
        NoReward,
        reflect_deterministic,
        reflect_with_llm,
        write_reflection,
    )
    from ariadne.learning.runs import load_run

    reflector = None
    if llm:
        # Key-guard before load_run or any anthropic import (mirrors `distil --llm`).
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print(
                "ANTHROPIC_API_KEY is not set — export it to use --llm (the Claude reflector).",
                file=sys.stderr,
            )
            return 2
        from ariadne.learning.reflect import ClaudeReflector

        reflector = ClaudeReflector()

    run = load_run(run_dir)
    try:
        if reflector is not None:
            reflection = reflect_with_llm(run, call_llm=reflector.call_llm, model=reflector.model)
        else:
            reflection = reflect_deterministic(run)
    except NoReward as exc:
        print(f"Cannot reflect on {run_dir}: {exc}", file=sys.stderr)
        return 1

    md, js = write_reflection(out or run_dir, reflection)
    if not reflection.findings:
        print(f"No findings — every gold-anchored dimension is at its ideal. Wrote {md}.")
        return 0
    dims = ", ".join(sorted({f.dimension for f in reflection.findings}))
    print(
        f"Reflected on {run_dir}: {len(reflection.findings)} finding(s) [{dims}]. Wrote {md} + {js.name}."
    )
    print("Review the proposed refinements and ratify by acting on them — nothing is auto-applied.")
    return 0


def _run_compare(baseline: list[str], candidate: list[str], *, out: str | None = None) -> int:
    """Net a candidate's effect vs a baseline (the measured ratify step, ADR-0031).

    Exit code carries the verdict for scripting: ratify/neutral = 0, reject = 1, and an
    incomparable pairing (empty / unscored / different instance) = 2. Reads `eval.json`;
    never recomputes a score.
    """
    from ariadne.learning.netcheck import (
        IncomparableRuns,
        compare,
        comparison_dict,
        render_comparison_md,
    )
    from ariadne.learning.runs import load_run

    try:
        net = compare([load_run(d) for d in baseline], [load_run(d) for d in candidate])
    except IncomparableRuns as exc:
        print(f"Cannot compare: {exc}", file=sys.stderr)
        return 2

    print(render_comparison_md(net))
    if out:
        Path(out).write_text(json.dumps(comparison_dict(net), indent=2), encoding="utf-8")
        print(f"Wrote {out}")
    return 1 if net.verdict == "reject" else 0


def _make_ratify_runner(*, with_sql: bool, with_semantic: bool):
    """The live arm runner: one real workup per trial into an isolated dir, returning its run dir.

    Each trial gets its own ``out_root/<arm>/trial-N`` so every trial's ``latest`` is distinct (a
    shared root would have later trials clobber the pointer). Loads the arm's skills from its staged
    plugin dir — the with/without-candidate toggle (ADR-0034). Gated: real workups cost API + stores.
    """
    seq = {"i": 0}

    def runner(*, arm, entity: str, dataset: str, env: dict[str, str], out_root: Path) -> Path:
        seq["i"] += 1
        trial_root = Path(out_root) / arm.label / f"trial-{seq['i']}"
        asyncio.run(
            run_workup(
                entity,
                str(trial_root),
                env,
                dataset=dataset,
                with_sql=with_sql,
                with_semantic=with_semantic,
                skills_plugin=arm.plugin_path,
            )
        )
        return trial_root / dataset / slug(entity) / "latest"

    return runner


def _make_ratify_scorer():
    """The live scorer: score a trial against the planted-needle fixture, persisting its eval.json
    (the same eval `ariadne eval` runs — the single scorer; `compare` only reads the output)."""
    from ariadne.evaluation.needle import FIXTURES, score_workup_dir

    def scorer(run_dir, fixture: str) -> None:
        report = score_workup_dir(str(run_dir), FIXTURES[fixture])
        write_eval_json(str(run_dir), report, fixture)

    return scorer


def _run_ratify(
    candidate_skill: str,
    *,
    entity: str,
    dataset: str = "synthetic",
    fixture: str = "halberd",
    trials: int = 3,
    out: str = "runs",
    base_skills: list[str] | None = None,
    apply_: bool = False,
    with_sql: bool = False,
    with_semantic: bool = False,
    env: dict[str, str],
    runner=None,
    scorer=None,
    skills_root: str | Path = Path(".claude/skills"),
) -> int:
    """Produce paired with/without-skill runs, net their effect, optionally freeze (ADR-0034).

    The live, expensive end of propose -> ratify -> freeze: runs ``2 * trials`` real workups (the
    candidate skill OFF vs ON) over the same instance and nets them via `compare`, gating on whether
    the skill actually fired (SkillTester — else the delta is ambient variance). ``--apply`` freezes
    the skill only on a clean ratify; default is propose-only. Exit code mirrors `compare`:
    reject = 1, ratify / neutral / abstain = 0, incomparable = 2.
    """
    from ariadne.learning.netcheck import IncomparableRuns
    from ariadne.learning.ratify import apply_ratification, render_ratification_md, run_ratify

    if not (Path(candidate_skill) / "SKILL.md").is_file():
        print(f"No SKILL.md under {candidate_skill} to ratify.", file=sys.stderr)
        return 2
    if runner is None:
        if not env.get("ANTHROPIC_API_KEY"):
            print(
                "ANTHROPIC_API_KEY is not set — `ratify` runs live workups (real spend); export it.",
                file=sys.stderr,
            )
            return 2
        runner = _make_ratify_runner(with_sql=with_sql, with_semantic=with_semantic)
    if scorer is None:
        scorer = _make_ratify_scorer()

    try:
        outcome = run_ratify(
            candidate_skill=candidate_skill,
            entity=entity,
            dataset=dataset,
            fixture=fixture,
            n=trials,
            env=env,
            out_root=out,
            base_skills=base_skills or [".claude/skills/entity-workup"],
            runner=runner,
            scorer=scorer,
        )
    except IncomparableRuns as exc:
        print(f"Cannot ratify: {exc}", file=sys.stderr)
        return 2

    print(render_ratification_md(outcome))
    if apply_:
        if outcome.verdict == "ratify":
            dest = apply_ratification(candidate_skill, skills_root=skills_root)
            print(f"Applied — froze `{outcome.expected_skill}` to {dest} (ratified on a net gain).")
        else:
            print(
                f"Not applied — verdict is {outcome.verdict!r}, not a clean ratify.",
                file=sys.stderr,
            )
    return 1 if outcome.verdict == "reject" else 0


def _run_eval(workup_dir: str, fixture_name: str = "halberd", reconcile: str | None = None) -> int:
    """Score an existing workup against a planted-needle fixture (no API key needed)."""
    msg = _missing_workup(workup_dir, "note.md", "provenance.jsonl")
    if msg:
        print(msg, file=sys.stderr)
        return 2
    report = score_workup_dir(workup_dir, FIXTURES[fixture_name])
    rec = None
    with eval_span(report.entity, fixture_name):
        record_eval_metrics(report, fixture=fixture_name)
        if reconcile is not None:
            rec = score_reconciliation_dir(workup_dir, RECON_FIXTURES[reconcile])
            record_reconciliation_metrics(rec, fixture=reconcile)
    write_eval_json(workup_dir, report, fixture_name, reconciliation=rec)  # surfaced in the report
    merge_scores(
        Path(workup_dir),
        {
            "eval": {
                "grounded": report.grounded,
                "recall": report.recall,
                "trajectory": report.trajectory,
            }
        },
    )
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
    if report.context_utilization is not None:
        line += f" utilization={report.context_utilization:.2f}"  # descriptive, never gates
    if report.citation_coverage is not None:
        line += f" coverage={report.citation_coverage:.2f}"  # descriptive, never gates (ADR-0023)
    print(line)
    if rec is not None:
        print(
            f"Reconciliation [{rec.entity}/{reconcile}]: reconciliation={rec.reconciliation:.2f} "
            f"(corroboration={rec.corroboration:.2f} conflict={rec.conflict:.2f}) "
            f"{rec.handled}/{rec.total} cases"
        )
    return 0 if report.grounded else 1


def _load_unified_verdict(workup_dir: Path, governance: GovernanceReport):
    """Fold the four persisted signals into one verdict, or None if quality artifacts absent.

    The read-only axis uses the *freshly recomputed* ``governance`` audit (verify-
    don't-trust); the citation / tradecraft / egress axes are read from the run's own
    persisted artifacts (those gates already ran at workup time, so the recorded
    result is authoritative). Returns None when ``citations.json`` is missing, so a
    ledger-only dir degrades to the plain read-only gate.
    """
    from ariadne.provenance.assurance import build_verdict
    from ariadne.provenance.citations import CitationReport, CoverageStats
    from ariadne.provenance.tradecraft import TradecraftReport

    cit_path = Path(workup_dir) / "citations.json"
    if not cit_path.exists():
        return None
    cit = json.loads(cit_path.read_text(encoding="utf-8"))
    citations = CitationReport(
        ok=cit.get("ok", False),
        cited=cit.get("cited", []),
        dangling=cit.get("dangling", []),
        unused=cit.get("unused", []),
        uncited=cit.get("uncited", []),
        unsupported=cit.get("unsupported", []),
    )
    cov_block = cit.get("coverage")
    coverage = (
        CoverageStats(
            cov_block.get("covered", 0), cov_block.get("total", 0), cov_block.get("after")
        )
        if cov_block
        else None
    )

    tc_path = Path(workup_dir) / "tradecraft.json"
    tc = json.loads(tc_path.read_text(encoding="utf-8")) if tc_path.exists() else {}
    tradecraft = TradecraftReport(
        standard_terms=[tuple(t) for t in tc.get("standard_terms", [])],
        nonstandard_terms=tc.get("nonstandard_terms", []),
        has_confidence_statement=tc.get("has_confidence_statement", False),
    )

    gov_path = Path(workup_dir) / "governance.json"
    gov = json.loads(gov_path.read_text(encoding="utf-8")) if gov_path.exists() else {}
    egress = gov.get("profile", {}).get("egress", "inherit")

    return build_verdict(
        governance=governance,
        citations=citations,
        coverage=coverage,
        tradecraft=tradecraft,
        egress=egress,
    )


def _run_governance(workup_dir: str) -> int:
    """Re-audit a persisted workup and report the unified assurance verdict (offline gate).

    Recomputes the read-only audit from ``provenance.jsonl`` rather than trusting
    ``governance.json`` — the same verify-don't-trust posture the audit takes — then
    folds it with the run's persisted citation / tradecraft / egress signals into one
    weakest-link verdict. Gating precedence mirrors the live workup: a read-only
    breach exits 3 (security outranks all), a persisted citation failure exits 1
    (analytic), advisory/clean exits 0. No API key needed.
    """
    ledger_path = Path(workup_dir) / "provenance.jsonl"
    if not ledger_path.exists():
        print(f"No provenance.jsonl in {workup_dir!r} — nothing to audit.", file=sys.stderr)
        return 2
    report = audit_read_only(ProvenanceLedger.read_jsonl(ledger_path))
    verdict = _load_unified_verdict(Path(workup_dir), report)

    if verdict is not None:
        print(f"Assurance verdict — {workup_dir}: {verdict.status.upper()}")
        for axis in verdict.axes:
            mark = {"pass": "ok", "fail": "FAIL", "advisory": "advisory"}.get(axis.status, "·")
            print(f"  [{mark:<8}] {axis.label:<20} {axis.detail}")
    elif report.ok:
        # Ledger-only dir (e.g. a committed fixture): plain read-only OK message.
        print(f"Governance OK — {workup_dir}: read-only contract upheld.")

    if not report.ok:
        verbs = sorted({w["verb"] for w in report.write_attempts})
        print(
            f"GOVERNANCE FAILED — {workup_dir}: read-only contract violated, "
            f"write verbs in the ledger {verbs}.",
            file=sys.stderr,
        )
        return 3
    if verdict is not None and not verdict.ok:
        print(f"GOVERNANCE FAILED — {workup_dir}: citation gate failed.", file=sys.stderr)
        return 1
    return 0


def _run_rubric(workup_dir: str, minimum: float | None = None) -> int:
    """Score a workup's note against the ICD-203 rubric with the live Claude judge.

    Needs ANTHROPIC_API_KEY + the 'rubric' extra. Informational by default; with
    ``--min`` it becomes a CI-gateable pass/fail on the overall score.
    """
    from ariadne.evaluation.judge import ClaudeAnalyticJudge
    from ariadne.evaluation.rubric import score_note_dir, write_rubric_json

    report = score_note_dir(workup_dir, ClaudeAnalyticJudge())
    write_rubric_json(workup_dir, report)  # surfaced in the report
    merge_scores(Path(workup_dir), {"rubric": {"score": report.overall}})
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


# Per-dataset capability cases: (dataset, entity, needle fixture). Both graph-only.
_VALIDATION_CASES: tuple[tuple[str, str, str], ...] = (
    ("synthetic", "Halberd", "halberd"),
    ("enron", "vince.kaminski@enron.com", "kaminski-aol"),
)


def _validate_profile(
    name: str,
    *,
    env: dict[str, str],
    timeout: float = 600.0,
    dataset: str | None = None,
    attempts: int = 3,
    runner=None,
    scorer=None,
) -> int:
    """Run a real workup with `name` against each dataset's planted needle under a
    budget; a dataset PASSes iff it grounds within `attempts` tries. Capability is
    "can the model do it" — a capable model varies run-to-run (it may surface the
    answer via a shorter path that under-logs the traversal), while an incapable or
    throughput-bound model fails every attempt. Returns 0 iff all datasets pass."""
    import shutil
    import tempfile
    from pathlib import Path

    from ariadne.evaluation.needle import FIXTURES, score_workup_dir
    from ariadne.profiles import load_profiles, resolve_profile

    resolve_profile(name, load_profiles(env))  # clear error if the name is not in the allowlist
    if runner is None and not env.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set — export it to validate a profile.", file=sys.stderr)
        return 2
    cases = [c for c in _VALIDATION_CASES if dataset is None or c[0] == dataset]
    if not cases:
        print(f"No validation case registered for dataset {dataset!r}.", file=sys.stderr)
        return 2
    run = runner or run_workup
    all_pass = True
    for ds, entity, fixture in cases:
        grounded = False
        detail = "no attempt completed"
        for attempt in range(1, attempts + 1):
            out_root = tempfile.mkdtemp(prefix="ariadne-validate-")
            try:
                rc = asyncio.run(
                    _run_under_budget(run(entity, out_root, env, dataset=ds, profile=name), timeout)
                )
                if rc is None:
                    detail = f"exceeded the {timeout:.0f}s budget (throughput-bound)"
                    continue
                out_dir = str(Path(out_root) / ds / slug(entity) / "latest")
                report = scorer(out_dir) if scorer else score_workup_dir(out_dir, FIXTURES[fixture])
                detail = f"recall={report.recall:.2f} trajectory={report.trajectory:.2f}"
                if report.grounded:
                    grounded = True
                    print(f"  {ds:<10} PASS (attempt {attempt}/{attempts}) — {detail}")
                    break
            finally:
                shutil.rmtree(out_root, ignore_errors=True)
        if not grounded:
            print(f"  {ds:<10} FAIL after {attempts} attempt(s) — last: {detail}", file=sys.stderr)
            all_pass = False
    print(f"Profile {name!r}: {'PASS' if all_pass else 'FAIL'} ({len(cases)} dataset(s) checked).")
    return 0 if all_pass else 1


def _run_profiles(env: dict[str, str]) -> int:
    """List the curated model profiles this deployment offers."""
    from ariadne.profiles import load_profiles

    for name, p in sorted(load_profiles(env).items()):
        model = p.model or "(deployment default)"
        print(f"{name:<14} egress={p.egress:<9} model={model}")
        if p.description:
            print(f"{'':<14} {p.description}")
    return 0


def _hard_exit(code: int) -> None:
    """Flush stdio and hard-exit the process with ``code``.

    research(2026-06): HF streaming can leave the interpreter unable to exit — a known
    upstream bug (datasets#7467; the gc.collect fix in PR #8176 covers only the parquet
    path on pyarrow<=24, not the audio stream worldspeech uses). After ``index`` the
    canonical records are already durably committed to the live stores, so this one-shot
    loader hard-exits rather than hang on wedged library threads (``_run_index`` emits no
    spans/metrics, so nothing is lost). A module-level seam so tests can neutralize it.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


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
    skills_plugin: str | Path | None = None,
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
    # Skills: the project `entity-workup` by default (the SDK auto-allows the Skill tool and sets
    # setting_sources). `ratify` (ADR-0034) instead points the workup at a staged per-arm plugin
    # dir to toggle a candidate skill in/out — then the Skill tool must be allowed explicitly so
    # the plugin's skills can fire, and project skills are left out for clean arm isolation.
    if skills_plugin is not None:
        extra["plugins"] = [{"type": "local", "path": str(skills_plugin)}]
        extra["skills"] = []
        if "Skill" not in allowed_tools:
            allowed_tools = [*allowed_tools, "Skill"]
    else:
        extra["skills"] = ["entity-workup"]
    return ClaudeAgentOptions(
        mcp_servers=mcp_servers,
        allowed_tools=allowed_tools,
        system_prompt=_SYSTEM_PROMPT,
        permission_mode="default",
        hooks={"PostToolUse": matchers},
        **extra,
    )


def build_repair_options(model: str | None) -> ClaudeAgentOptions:
    """Tool-less options for the post-hoc citation-repair pass: no MCP servers and no
    tools, so the pass can only rewrite text — never retrieve or mutate (ADR-0022)."""
    extra: dict[str, Any] = {}
    if model is not None:
        extra["model"] = model
    return ClaudeAgentOptions(
        mcp_servers={},
        allowed_tools=[],
        system_prompt=_REPAIR_SYSTEM_PROMPT,
        permission_mode="default",
        **extra,
    )


def make_repair_caller(model: str | None) -> Callable[[str], Awaitable[str]]:
    """Return an injected ``call_llm`` that runs one tool-less repair query (P-Cite)."""
    options = build_repair_options(model)

    async def _call(prompt: str) -> str:
        parts: list[str] = []
        result_text: str | None = None
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                parts.extend(b.text for b in message.content if isinstance(b, TextBlock))
            elif isinstance(message, ResultMessage):
                result_text = message.result
        return (result_text or "\n".join(parts)).strip()

    return _call


def workup_exit_code(
    *, governance: GovernanceReport, strict: bool, had_error: bool, citations_ok: bool
) -> int:
    """Resolve a workup's process exit code.

    Under ``--strict`` a read-only contract breach exits 3 and takes precedence
    over the analytic-quality failures (exit 1) — a mutated evidence store taints
    the whole product. Default (non-strict) keeps a breach advisory.
    """
    # research(2026-06): distinct exit 3 (not a reused 1) lets CI route a
    # safety-contract breach differently from an analytic miss — the convention
    # for policy/security gates. sysexits EX_NOPERM=77 rejected for consistency
    # with this CLI's existing 1 (analytic failure) / 2 (precondition) scheme.
    if strict and not governance.ok:
        return 3
    if had_error or not citations_ok:
        return 1
    return 0


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
    strict: bool = False,
    repair: bool = True,
    skills_plugin: str | Path | None = None,
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
        skills_plugin=skills_plugin,
    )
    verifier = None
    if with_entail:
        from ariadne.provenance.entailment import HHEMVerifier

        verifier = HHEMVerifier()
    prompt = f"Run entity workup on: {entity}"

    note_parts: list[str] = []
    result_text: str | None = None
    had_error: bool = False
    result_cost: float | None = None
    result_usage: dict | None = None
    result_model_usage: dict | None = None
    skills_seen: set[str] = set()  # which Agent Skills fired (ADR-0034's SkillTester gate)
    with workup_span(entity, dataset, semantic=with_semantic, sql=with_sql):
        started = time.monotonic()
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                note_parts.extend(
                    block.text for block in message.content if isinstance(block, TextBlock)
                )
                # Hooks never fire for Skill (it is prompt-expansion, not a piped tool —
                # anthropics/claude-code#43630), so read the invocation off the stream here.
                skills_seen |= skill_invocations(message.content)
            elif isinstance(message, ResultMessage):
                result_text = message.result
                had_error = bool(getattr(message, "is_error", False))
                result_cost = message.total_cost_usd
                result_usage = message.usage
                result_model_usage = message.model_usage
        note = (result_text or "\n".join(note_parts)).strip()
        if repair:
            outcome = await repair_citations_loop(
                note, ledger, call_llm=make_repair_caller(prof.model), verifier=verifier
            )
            note, report = outcome.note, outcome.report
            coverage_before = outcome.coverage_before
            coverage_after = outcome.coverage_after
            repair_passes = outcome.passes_run
        else:
            report = validate_citations(note, ledger, verifier=verifier)
            coverage_before = None
            coverage_after = citation_coverage(note)
            repair_passes = None
        elapsed = time.monotonic() - started
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
        trace_hex = current_trace_hex()
        out_dir = run_dir(out_root, dataset, entity, trace_hex=trace_hex)
        write_outputs(
            out_dir,
            entity=entity,
            note=note,
            ledger=ledger,
            report=report,
            tradecraft=tradecraft,
            governance=governance,
            profile=prof,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
            repair_passes=repair_passes,
        )
        # Additive: persist the traversed entity neighborhood (for the report's
        # network view) + render the self-contained interactive report alongside
        # the existing artifacts (ADR-0017); never replaces note.md or the JSON.
        from ariadne.graph.subgraph import write_subgraph
        from ariadne.report.html import write_report

        write_subgraph(out_dir, entity, os.environ)
        write_report(out_dir)

    print(
        f"Wrote {out_dir}/note.md + report.html ({len(ledger.entries)} graph calls cited) "
        f"in {elapsed:.1f}s."
    )
    if repair_passes is not None and coverage_after.fraction is not None:
        before = coverage_before.fraction if coverage_before is not None else None
        delta = f" (+{coverage_after.fraction - before:.0%})" if before is not None else ""
        passes = f"{repair_passes} repair pass{'' if repair_passes == 1 else 'es'}"
        print(f"Citation coverage {coverage_after.fraction:.0%}{delta} after {passes}.")
    if tradecraft.nonstandard_terms:
        print(
            "Tradecraft (advisory): non-standard estimative terms "
            f"{sorted(set(tradecraft.nonstandard_terms))} — prefer ICD-203 bands.",
            file=sys.stderr,
        )
    if not governance.ok:
        verbs = sorted({w["verb"] for w in governance.write_attempts})
        posture = "FAILED (--strict)" if strict else "advisory"
        print(
            f"GOVERNANCE [{posture}]: read-only contract violated — write verbs in the "
            f"ledger {verbs}. The analytic loop must not mutate the evidence stores.",
            file=sys.stderr,
        )
    if had_error:
        print("agent run reported an error", file=sys.stderr)
    if not report.ok:
        print(
            f"Citation check FAILED — dangling: {report.dangling} · "
            f"uncited claims: {len(report.uncited)} · "
            f"unsupported claims: {len(report.unsupported)}",
            file=sys.stderr,
        )
    code = workup_exit_code(
        governance=governance, strict=strict, had_error=had_error, citations_ok=report.ok
    )
    write_manifest(
        out_dir,
        build_workup_manifest(
            run_directory=out_dir,
            entity=entity,
            dataset=dataset,
            model=", ".join(sorted(result_model_usage)) if result_model_usage else prof.model,
            profile=prof.name,
            params={
                "sql": with_sql,
                "semantic": with_semantic,
                "entail": with_entail,
                "strict": strict,
            },
            duration_s=elapsed,
            exit_code=code,
            trace_hex=trace_hex,
            cost_usd=result_cost,
            usage=result_usage,
            scores=scores_from_reports(report, tradecraft, governance),
            skills_invoked=sorted(skills_seen),
        ),
    )
    update_latest(out_dir.parent, out_dir.name)
    return code


def main(argv: list[str] | None = None) -> int:
    # Load a local .env (cp .env.example .env) from the working dir, without
    # clobbering already-exported vars. usecwd=True searches up from where the
    # user runs the command (not from this installed module's location).
    load_dotenv(find_dotenv(usecwd=True), override=False)
    setup_telemetry()
    discover_and_register(dict(os.environ))  # ADR-0025: register ARIADNE_MAPPINGS user datasets
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "eval":
        return _run_eval(args.workup_dir, args.fixture, reconcile=args.reconcile)
    if args.command == "index":
        # Hard-exit on *either* path (clean load, or a stall TimeoutError from the guard)
        # so a wedged HF streaming thread can never hang interpreter shutdown. See _hard_exit.
        try:
            rc = _run_index(args.dataset, dict(os.environ), semantic=args.semantic)
        except BaseException:
            traceback.print_exc()
            _hard_exit(1)
            raise  # unreachable in the real CLI; _hard_exit is a no-op only under test
        _hard_exit(rc)
        return rc
    if args.command == "profiles":
        if args.validate:
            return _validate_profile(
                args.validate,
                env=dict(os.environ),
                timeout=args.timeout,
                dataset=args.dataset,
                attempts=args.attempts,
            )
        return _run_profiles(dict(os.environ))
    if args.command == "governance":
        return _run_governance(args.workup_dir)
    if args.command == "report":
        return _run_report(args.workup_dir)
    if args.command == "map":
        return _run_map(
            args.name,
            args.out,
            args.schema,
            dsn=args.dsn,
            dsn_env=args.dsn_env,
            llm=args.llm,
            ontology=args.ontology,
        )
    if args.command == "distil":
        return _run_distil(args.run_dir, name=args.name, out=args.out, llm=args.llm, into=args.into)
    if args.command == "reflect":
        return _run_reflect(args.run_dir, out=args.out, llm=args.llm)
    if args.command == "compare":
        return _run_compare(args.baseline, args.candidate, out=args.out)
    if args.command == "ratify":
        return _run_ratify(
            args.candidate_skill,
            entity=args.entity,
            dataset=args.dataset,
            fixture=args.fixture,
            trials=args.trials,
            out=args.out,
            base_skills=args.base_skill,
            apply_=args.apply,
            with_sql=args.sql,
            with_semantic=args.semantic,
            env=dict(os.environ),
        )
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "ANTHROPIC_API_KEY is not set — export it to run the live agent loop.",
            file=sys.stderr,
        )
        return 2
    if args.command == "rubric":
        return _run_rubric(args.workup_dir, args.min)
    # Fast-fail before the paid agent loop if a store the run needs isn't up (the #1
    # first-run stumble): print how to start it, exit cleanly, spend nothing.
    unreachable = workup_preflight(dict(os.environ), with_sql=args.sql, with_semantic=args.semantic)
    if unreachable:
        print(unreachable, file=sys.stderr)
        return 2
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
            strict=args.strict,
            repair=args.repair,
        )
    )
