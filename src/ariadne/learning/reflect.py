"""Reflexion over the eval harness — diagnose + reflect, grounded and gold-free (ADR-0030).

B3 of the adaptive epic (ADR-0020): an eval-triggered reflection that diagnoses an
under-performing run's dimensions and proposes refinements for a human to ratify. Two
boundaries close the two measurable reward-hacking vectors:

- **No evaluator tampering** — the reflection proposes refinements to ratified artifacts; it
  never edits the eval scorers/gates/code (ADR-0020's hard boundary).
- **No train/test leakage** — the reflection reads only the run's *own* artifacts (the eval
  SCORES, trajectory, note, citations) and never the held-out gold. Own-evidence findings cite
  the agent's own uncited/dangling claims; score-triggered findings ground the proposed fix in
  the trajectory *shape*, never the missed answer.

Propose-only (a human breaks the in-context self-refine loop). Deterministic diagnosis +
``--llm`` reflexion, mirroring the B2 distiller.

# research(2026-06): Reflexion verbal RL over episodic self-critique (arXiv 2303.11366);
# the two reward-hacking vectors are evaluator tampering + train/test leakage (arXiv 2603.11337);
# in-context reward hacking lives in closed self-refine loops (arXiv 2407.04549 / 2402.06627) ->
# propose-only; intrinsic self-correction is not a gate -> the external eval stays it. ADR-0030.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ariadne.learning import DEFAULT_MODEL
from ariadne.learning.runs import (
    RunArtifacts,
    fmt_score,
    move_sequence,
    prerequisites,
    query_text,
    truncate,
)

if TYPE_CHECKING:
    from collections.abc import Callable

# Gold-anchored dimensions whose ideal is known, so "below it" is a non-arbitrary shortfall.
_SCORE_TRIGGERED = ("recall", "trajectory", "supporting_fact_f1")
# Descriptive dimensions reported as context, never as defects (no arbitrary thresholds).
_CONTEXT_DIMS = ("pivot_burden", "queries_run", "context_utilization")


class NoReward(Exception):
    """No external verifiable reward (no eval.json) — reflection has nothing to anchor on."""


@dataclass(frozen=True)
class Finding:
    """One diagnosed shortfall, grounded in cited, gold-free evidence."""

    dimension: str
    score: float | bool | None
    ideal: float | bool | None
    kind: str  # "own-evidence" | "score-triggered" | "behavioral"
    evidence: list[str]


@dataclass(frozen=True)
class Reflection:
    """A proposed reflection: the structured findings, the rendered prose, the JSON record."""

    findings: tuple[Finding, ...]
    reflection_md: str
    structured: dict[str, Any]


# --- diagnosis (deterministic, gold-free) ------------------------------------------


def require_reward(run: RunArtifacts) -> None:
    """Raise :class:`NoReward` unless the run carries an eval (the external verifiable reward).

    Mirrors the B2 certification gate: reflexion is reliable only against an external truth
    signal, so an unscored run is refused rather than reflected on with the model's own
    (same-blind-spot) judgment.
    """
    if not run.eval_scores:
        raise NoReward(
            "run has no eval.json — reflection needs the external verifiable reward. "
            "Run `ariadne eval <dir>` first."
        )


def _trajectory_shape(run: RunArtifacts) -> list[str]:
    """The agent's OWN trajectory structure — capabilities/phases used. Never the gold."""
    caps = ", ".join(prerequisites(run)) or "none"
    phases = " -> ".join(ph for ph, _ in move_sequence(run.provenance)) or "none"
    return [
        f"capabilities used: {caps}",
        f"phase sequence: {phases}",
        f"{len(run.provenance)} tool call(s) in the trajectory",
    ]


def _duplicate_queries(provenance: list[dict[str, Any]]) -> list[str]:
    """Exact-duplicate query texts in the ledger — a non-arbitrary, gold-free inefficiency."""
    seen: dict[str, str] = {}
    dups: list[str] = []
    for entry in provenance:
        text = " ".join(query_text(entry).split())
        if not text:
            continue
        if text in seen:
            dups.append(
                f"[{seen[text]}] and [{entry.get('id', '?')}] ran the same query: "
                f"{truncate(text, 120)}"
            )
        else:
            seen[text] = entry.get("id", "?")
    return dups


def _citation_evidence(citations: dict[str, Any]) -> list[str]:
    evidence = [f"uncited claim: {truncate(c, 160)}" for c in citations.get("uncited", [])]
    evidence += [
        f"dangling citation: [cite:{g}] resolves to no ledger entry"
        for g in citations.get("dangling", [])
    ]
    evidence += [f"unsupported claim: {truncate(c, 160)}" for c in citations.get("unsupported", [])]
    return evidence


def diagnose(run: RunArtifacts) -> list[Finding]:
    """Diagnose under-performing dimensions, each grounded in the run's own evidence.

    Gold-free by construction: reads the eval SCORES + the agent's own artifacts, never the
    held-out gold. Returns ``[]`` for a run whose every gold-anchored dimension is at ideal.
    """
    require_reward(run)
    ev = run.eval_scores
    citations = run.citations or {}
    findings: list[Finding] = []

    # own-evidence: a citation shortfall cites the agent's OWN uncited/dangling/unsupported claims
    coverage = ev.get("citation_coverage")
    coverage_low = (
        isinstance(coverage, (int, float)) and not isinstance(coverage, bool) and coverage < 1.0
    )
    if coverage_low or ev.get("grounded") is False:
        evidence = _citation_evidence(citations)
        if (
            evidence
        ):  # only emit when there is real own-evidence (else the recall finding covers it)
            dim, score, ideal = (
                ("citation_coverage", coverage, 1.0)
                if coverage is not None
                else ("grounded", False, True)
            )
            findings.append(Finding(dim, score, ideal, "own-evidence", evidence))

    # score-triggered: a gold-anchored dim below ideal; the fix grounds in the trajectory shape
    shape = _trajectory_shape(run)
    for dim in _SCORE_TRIGGERED:
        score = ev.get(dim)
        if isinstance(score, (int, float)) and not isinstance(score, bool) and score < 1.0:
            findings.append(Finding(dim, float(score), 1.0, "score-triggered", shape))

    # behavioral: exact-duplicate queries (non-arbitrary, gold-free)
    dups = _duplicate_queries(run.provenance)
    if dups:
        findings.append(Finding("redundant-queries", None, None, "behavioral", dups))

    return findings


# --- rendering ---------------------------------------------------------------------


def _identity(run: RunArtifacts) -> dict[str, str]:
    m = run.manifest or {}
    ev = run.eval_scores
    return {
        "run_id": m.get("run_id") or Path(run.run_dir).name,
        "dataset": m.get("dataset", ""),
        "entity": m.get("entity") or ev.get("entity", ""),
        "fixture": ev.get("fixture", ""),
    }


def _context(run: RunArtifacts) -> dict[str, Any]:
    ev = run.eval_scores
    return {k: ev[k] for k in _CONTEXT_DIMS if k in ev}


def _findings_block(findings: tuple[Finding, ...]) -> str:
    out: list[str] = ["## Findings", ""]
    for i, f in enumerate(findings, 1):
        score = "" if f.score is None else f" = {fmt_score(f.score)}"
        ideal = "" if f.ideal is None else f" (ideal {fmt_score(f.ideal)})"
        out.append(f"### {i}. {f.dimension}{score}{ideal} · {f.kind}")
        out += [f"- {e}" for e in f.evidence]
        if f.kind == "score-triggered":
            out.append(
                "- *(the external score flags a shortfall; the fix is a procedural hypothesis "
                "from the trajectory shape, not the held-out gold)*"
            )
        out.append("")
    return "\n".join(out)


def _context_block(context: dict[str, Any]) -> str:
    if not context:
        return ""
    lines = ["## Context (reported, not graded)", ""]
    for k, v in context.items():
        caveat = (
            " — never-gated; exploratory / negative-confirmation retrieval legitimately lowers "
            "it (ADR-0019)"
            if k == "context_utilization"
            else ""
        )
        lines.append(f"- {k} = {fmt_score(v)}{caveat}")
    return "\n".join(lines) + "\n"


def _render_md(
    run: RunArtifacts,
    findings: tuple[Finding, ...],
    context: dict[str, Any],
    *,
    llm_body: str | None = None,
) -> str:
    ident = _identity(run)
    head = f"# Reflection — {ident['entity']} ({ident['run_id']})\n\n"
    if not findings:
        return (
            head
            + "No findings: every gold-anchored dimension is at its ideal. **Nothing to refine.**\n\n"
            + _context_block(context)
        )
    intro = (
        f"The external eval (the verifiable reward) flags **{len(findings)}** dimension(s) to "
        "refine. Grounded only in the run's own evidence — never the held-out gold; a human "
        "ratifies any proposed refinement.\n\n"
    )
    middle = (llm_body.strip() + "\n\n") if llm_body else ""
    return head + intro + middle + _findings_block(findings) + "\n" + _context_block(context)


def _structured(
    run: RunArtifacts, findings: tuple[Finding, ...], context: dict[str, Any], reflected_by: str
) -> dict[str, Any]:
    return {
        "run": _identity(run),
        "scores": run.eval_scores,
        "findings": [asdict(f) for f in findings],
        "context": context,
        "reflected_by": reflected_by,
        "gold_free": True,
    }


def reflect_deterministic(run: RunArtifacts) -> Reflection:
    """Diagnose + render a structured, cited reflection (no model, no proposed prose)."""
    findings = tuple(diagnose(run))
    context = _context(run)
    return Reflection(
        findings=findings,
        reflection_md=_render_md(run, findings, context),
        structured=_structured(run, findings, context, "deterministic"),
    )


# --- the --llm reflexion -----------------------------------------------------------


def build_reflect_prompt(run: RunArtifacts, findings: tuple[Finding, ...]) -> str:
    """Ground the model in the findings (its own evidence) + the note. Never the gold."""
    blocks = []
    for f in findings:
        score = "" if f.score is None else f" = {fmt_score(f.score)}"
        blocks.append(
            f"- {f.dimension}{score} ({f.kind}):\n" + "\n".join(f"    - {e}" for e in f.evidence)
        )
    return (
        "Reflect on this under-performing intelligence-analysis workup and propose concrete "
        "refinements. An external eval (the verifiable reward) flagged the shortfalls below; "
        "each is grounded in the run's OWN evidence. Do NOT invent the facts the run may have "
        "missed — you do not have the answer key; ground every proposed fix in the evidence "
        "given and the trajectory.\n\n"
        "## Flagged findings\n" + "\n".join(blocks) + "\n\n"
        f"## The note it produced\n{truncate(run.note, 2000)}\n\n"
        "Write a brief post-mortem, then for each finding a concrete proposed refinement to a "
        "reusable artifact (an analytic skill, a query strategy, or a mapping) that a human "
        "could ratify. Keep the citation discipline. Submit it with the propose_reflection tool."
    )


def reflect_with_llm(
    run: RunArtifacts,
    *,
    call_llm: Callable[[str], dict[str, Any]],
    model: str = DEFAULT_MODEL,
) -> Reflection:
    """Run the reflexion move over the diagnosed findings via an injected LLM seam.

    Short-circuits to the deterministic reflection when there is nothing to refine (no API
    call). The structured findings are computed deterministically; the model writes only the
    post-mortem + proposed refinements, grounded in the evidence it is given (never the gold).
    """
    findings = tuple(diagnose(run))
    context = _context(run)
    if not findings:
        return reflect_deterministic(run)
    proposal = call_llm(build_reflect_prompt(run, findings))
    body = proposal.get("reflection")
    if not body:
        raise RuntimeError(
            "reflector returned an incomplete propose_reflection call (missing/empty: "
            "reflection); the response was likely truncated — raise max_tokens or retry."
        )
    return Reflection(
        findings=findings,
        reflection_md=_render_md(run, findings, context, llm_body=body),
        structured={**_structured(run, findings, context, f"llm:{model}"), "reflection": body},
    )


# --- writing the reflection beside the run's artifacts -----------------------------


def write_reflection(run_dir: str | Path, reflection: Reflection) -> tuple[Path, Path]:
    """Write ``reflection.md`` + ``reflection.json`` into ``run_dir``; return both paths.

    A proposal a human reads and acts on — nothing is auto-applied (propose-only breaks the
    in-context self-refine loop where reward hacking lives).
    """
    d = Path(run_dir)
    d.mkdir(parents=True, exist_ok=True)
    md, js = d / "reflection.md", d / "reflection.json"
    md.write_text(reflection.reflection_md, encoding="utf-8")
    js.write_text(json.dumps(reflection.structured, indent=2), encoding="utf-8")
    return md, js


# --- the live reflector (the adaptive extra; mirrors ClaudeSkillDistiller) ----------

_REFLECT_SYSTEM = (
    "You are a tradecraft mentor running a post-mortem on one under-performing "
    "intelligence-analysis workup. You are given the dimensions an external eval flagged and "
    "the run's own evidence — never the answer key. Reflect, then propose concrete refinements "
    "to reusable artifacts a human could ratify. Submit with the propose_reflection tool."
)

PROPOSE_REFLECTION_TOOL: dict[str, Any] = {
    "name": "propose_reflection",
    "description": (
        "Submit the reflection: a Markdown post-mortem plus, per flagged finding, a concrete "
        "proposed refinement to a reusable artifact (skill / query strategy / mapping)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "reflection": {
                "type": "string",
                "description": "Markdown: post-mortem + a concrete proposed refinement per finding",
            }
        },
        "required": ["reflection"],
    },
}


class ClaudeReflector:
    """An LLM reflector backed by the Claude Messages API (the ``adaptive`` extra).

    Mirrors :class:`ariadne.learning.distil.ClaudeSkillDistiller` — forced ``propose_reflection``
    tool-use, lazy ``anthropic`` import. No repair loop: a reflection has no deterministic
    structural validator (its gate is the source eval + human ratification).
    """

    def __init__(self, *, model: str = DEFAULT_MODEL, max_tokens: int = 4096) -> None:
        import importlib

        anthropic = importlib.import_module("anthropic")
        self._client: Any = anthropic.Anthropic()
        self._model = model
        self._max_tokens = max_tokens

    @property
    def model(self) -> str:
        return self._model

    def call_llm(self, prompt: str) -> dict[str, Any]:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=_REFLECT_SYSTEM,
            tools=[PROPOSE_REFLECTION_TOOL],
            tool_choice={"type": "tool", "name": "propose_reflection"},
            messages=[{"role": "user", "content": prompt}],
        )
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == "propose_reflection":
                return dict(block.input)
        raise RuntimeError("reflector did not return a propose_reflection tool call")
