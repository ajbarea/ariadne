"""Distil an eval-certified workup trajectory into a structured analytic skill (ADR-0029).

B2 of the adaptive epic (ADR-0020): a high-scoring workup becomes a named, reusable,
declarative skill the harness auto-discovers on the next workup. The keystone is the
**certification gate** — only a run the eval harness scored ``grounded`` is a skill
source. That gate is the same deterministic verifiable reward (ADR-0019) the loop may
never edit, so the agent can only learn from what an external gate already certified
(the textbook defence against a self-improvement loop gaming itself).

Two distillers mirror A1's mapper (ADR-0026): the deterministic one *records* the
trajectory into a structured skeleton (it cannot generalize — the honest line); ``--llm``
runs the Trace2Skill move, generalizing the trajectory + note into transferable procedural
prose via forced tool-use behind the ``adaptive`` extra.

# research(2026-06): Trace2Skill (arXiv 2603.25158) trajectory-local lessons -> transferable
# declarative skills; SkillGen (arXiv 2605.10999) verifier-gates a skill on net gain (we gate
# on the source run's grounded verdict); SoK Agentic Skills (arXiv 2602.20867) a STRUCTURED
# store (granularity/prerequisites/reliability), not a flat cache; SkillTTA (arXiv 2605.16986)
# the ephemeral test-time alternative we rejected (bypasses ratification). ADR-0029.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import tomli_w

from ariadne.provenance.ledger import ProvenanceLedger

if TYPE_CHECKING:
    from collections.abc import Callable

_DEFAULT_MODEL = "claude-opus-4-8"

# MCP server name -> the capability it provides, for the skill's prerequisites.
_CAPABILITY = {"neo4j": "graph", "postgres": "relational", "ariadne": "semantic"}


class NotCertified(Exception):
    """A run is not an eligible skill source — it was not scored, or it did not ground."""


@dataclass(frozen=True)
class RunArtifacts:
    """What distillation reads from one immutable run dir (ADR-0021)."""

    run_dir: str
    provenance: list[dict[str, Any]]
    eval_scores: dict[str, Any]
    manifest: dict[str, Any] | None
    note: str


@dataclass(frozen=True)
class SkillCard:
    """The structured store record for a distilled skill (SoK Agentic Skills).

    ``reliability`` is the certifying eval; ``source`` ties the skill to the exact run it
    was distilled from — the citation ethos, extended from notes to skills.
    """

    name: str
    description: str
    granularity: str  # "atomic" | "composite"
    prerequisites: tuple[str, ...]
    reliability: dict[str, Any]
    source: dict[str, str]
    distilled_by: str  # "deterministic" | f"llm:{model}"

    def to_toml(self) -> str:
        return tomli_w.dumps(
            {
                "name": self.name,
                "description": self.description,
                "granularity": self.granularity,
                "prerequisites": list(self.prerequisites),
                "distilled_by": self.distilled_by,
                "reliability": dict(self.reliability),
                "source": dict(self.source),
            }
        )


@dataclass(frozen=True)
class DistilledSkill:
    """A proposed skill: the structured card + the rendered ``SKILL.md`` text."""

    card: SkillCard
    skill_md: str


# --- the filesystem seam -----------------------------------------------------------


def _read_json(path: Path) -> dict[str, Any] | None:
    import json

    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def load_run(run_dir: str | Path) -> RunArtifacts:
    """Load a run's trajectory, scores, manifest, and note. Missing eval -> ``{}``.

    ``load_run`` never refuses a run (a fixture-less live workup has no ``eval.json``);
    the certification gate, not the loader, is what rejects an uncertified run.
    """
    run_dir = Path(run_dir)
    prov = run_dir / "provenance.jsonl"
    note = run_dir / "note.md"
    return RunArtifacts(
        run_dir=str(run_dir),
        provenance=ProvenanceLedger.read_jsonl(prov) if prov.is_file() else [],
        eval_scores=_read_json(run_dir / "eval.json") or {},
        manifest=_read_json(run_dir / "manifest.json"),
        note=note.read_text(encoding="utf-8") if note.is_file() else "",
    )


# --- the certification gate (the keystone) -----------------------------------------


def certify(run: RunArtifacts) -> None:
    """Raise :class:`NotCertified` unless the run was scored and ``grounded`` is true.

    The eval harness is the external verifiable reward (ADR-0019); ``grounded`` is its
    binary verdict that the note's claims were retrieved, not invented. No eval at all
    means no verifiable reward — distillation refuses rather than learn from an unscored
    run (the honest capability line).
    """
    if not run.eval_scores:
        raise NotCertified(
            "run has no eval.json — distillation needs an eval-certified trajectory "
            "(the external verifiable reward). Run `ariadne eval <dir>` first."
        )
    if run.eval_scores.get("grounded") is not True:
        raise NotCertified(
            "run did not ground its claims (grounded is not true) — not a skill source. "
            "Distil only from a certified-good workup."
        )


# --- structural extraction (deterministic, always) ---------------------------------


def tool_family(tool: str) -> str:
    """The MCP server a tool belongs to: ``mcp__<server>__<name>`` -> ``<server>``."""
    parts = tool.split("__")
    return parts[1] if len(parts) >= 3 and parts[0] == "mcp" else "other"


def prerequisites(run: RunArtifacts) -> tuple[str, ...]:
    """The distinct, sorted capabilities (graph / relational / semantic) the run used."""
    caps = {_CAPABILITY.get(fam := tool_family(e.get("tool", "")), fam) for e in run.provenance}
    return tuple(sorted(caps))


def granularity(prereqs: tuple[str, ...]) -> str:
    """``composite`` if the skill spans more than one capability, else ``atomic``."""
    return "composite" if len(prereqs) > 1 else "atomic"


def _is_graph_schema_query(query: str) -> bool:
    q = query.lower()
    return any(
        p in q for p in ("db.labels", "db.relationshiptypes", "db.schema", "db.propertykeys")
    )


def _is_fulltext_sql(sql: str) -> bool:
    s = sql.lower()
    return any(p in s for p in ("@@", "tsquery", "tsvector", "ts_rank"))


def phase_of(entry: dict[str, Any]) -> str:
    """Categorize one trajectory entry into an analytic phase by tool family + query shape."""
    tool = entry.get("tool", "")
    fam = tool_family(tool)
    ti = entry.get("tool_input", {}) or {}
    if fam == "neo4j":
        if "get_neo4j_schema" in tool or _is_graph_schema_query(ti.get("query") or ""):
            return "graph-schema"
        return "graph-traversal"
    if fam == "postgres":
        if not tool.endswith("execute_sql"):
            return "relational-schema"
        sql = ti.get("sql") or ti.get("query") or ""
        return "free-text" if _is_fulltext_sql(sql) else "relational-query"
    if fam == "ariadne":
        return "free-text"
    return "other"


def _query_text(entry: dict[str, Any]) -> str:
    ti = entry.get("tool_input", {}) or {}
    return ti.get("query") or ti.get("sql") or ""


def _truncate(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _move_sequence(provenance: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """The trajectory collapsed into consecutive same-phase steps, in run order."""
    steps: list[tuple[str, list[dict[str, Any]]]] = []
    for entry in provenance:
        ph = phase_of(entry)
        if steps and steps[-1][0] == ph:
            steps[-1][1].append(entry)
        else:
            steps.append((ph, [entry]))
    return steps


def _source(run: RunArtifacts) -> dict[str, str]:
    m = run.manifest or {}
    ev = run.eval_scores
    return {
        "run_id": m.get("run_id") or Path(run.run_dir).name,
        "dataset": m.get("dataset", ""),
        "entity": m.get("entity") or ev.get("entity", ""),
        "git_sha": m.get("git_sha", ""),
        "fixture": ev.get("fixture", ""),
    }


def _reliability(eval_scores: dict[str, Any]) -> dict[str, Any]:
    """The certifying scores (drop the entity/fixture labels and any null fields)."""
    return {
        k: v for k, v in eval_scores.items() if k not in ("entity", "fixture") and v is not None
    }


def _default_name(source: dict[str, str]) -> str:
    return f"entity-workup-{source['dataset']}" if source["dataset"] else "entity-workup"


def _prose_join(items: tuple[str, ...]) -> str:
    """``("a",)`` -> ``a``; ``("a","b")`` -> ``a and b``; ``("a","b","c")`` -> ``a, b, and c``."""
    if len(items) <= 1:
        return items[0] if items else ""
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + ", and " + items[-1]


def _fmt_score(value: Any) -> str:
    """Round a float for human prose (the TOML sidecar keeps full precision)."""
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def _score_prose(reliability: dict[str, Any]) -> str:
    return ", ".join(f"{k}={_fmt_score(v)}" for k, v in reliability.items())


def _deterministic_description(prereqs: tuple[str, ...], source: dict[str, str]) -> str:
    return (
        f"Work up a target entity across the {_prose_join(prereqs)} stores and produce a "
        f"fully-cited analytic note. Distilled from a grounded "
        f"{source['fixture'] or source['dataset']} workup."
    )


def _yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return f'"{escaped}"'


def _render_skill_md(card: SkillCard, body: str) -> str:
    frontmatter = f"---\nname: {card.name}\ndescription: {_yaml_quote(card.description)}\n---\n\n"
    body = body.lstrip("\n")
    # LLM-proposed bodies usually open with their own H1 title; only add the card title
    # (the deterministic path's body has none) when the body brings no top-level heading.
    if body.startswith("# "):
        return f"{frontmatter}{body}\n"
    title = card.name.replace("-", " ").title()
    return f"{frontmatter}# {title}\n\n{body}\n"


def _deterministic_body(run: RunArtifacts, card: SkillCard) -> str:
    stores = "stores" if len(card.prerequisites) != 1 else "store"
    lines = [
        f"A grounded entity-workup distilled from the `{card.source['fixture']}` run over "
        f"the {_prose_join(card.prerequisites)} {stores}. This is a **deterministic record** "
        "of the moves a certified-good workup made; run `ariadne distil --llm` to generalize "
        "it into a transferable procedure.",
        "",
        "## Observed move sequence",
        "",
    ]
    for i, (phase, entries) in enumerate(_move_sequence(run.provenance), 1):
        tools = ", ".join(f"`{t}`" for t in sorted({e.get("tool", "") for e in entries}))
        lines.append(f"{i}. **{phase}** — {tools}")
        for entry in entries:
            query = _query_text(entry)
            if query:
                lines.append(f"   - `{_truncate(query, 140)}`")
    src = card.source
    rel = _score_prose(card.reliability)
    lines += [
        "",
        "## Interface & termination",
        "",
        "- **Input:** a target entity or organizational node.",
        "- **Output:** a fully-cited analytic note (every asserted fact carries a `[cite:gN]`).",
        "- **Done when:** the citation gate and the governance audit pass.",
        "",
        "## Provenance",
        "",
        f"Distilled from run `{src['run_id']}` (dataset `{src['dataset']}`, entity "
        f"`{src['entity']}`, git `{src['git_sha']}`).",
        "",
        f"Certifying eval (the verifiable reward): {rel}.",
    ]
    return "\n".join(lines)


def distil_deterministic(run: RunArtifacts, *, name: str | None = None) -> DistilledSkill:
    """Record a certified trajectory into a structured skill (no model, no generalization)."""
    certify(run)
    prereqs = prerequisites(run)
    source = _source(run)
    card = SkillCard(
        name=name or _default_name(source),
        description=_deterministic_description(prereqs, source),
        granularity=granularity(prereqs),
        prerequisites=prereqs,
        reliability=_reliability(run.eval_scores),
        source=source,
        distilled_by="deterministic",
    )
    return DistilledSkill(
        card=card, skill_md=_render_skill_md(card, _deterministic_body(run, card))
    )


# --- the --llm distiller (Trace2Skill generalization) ------------------------------


def _truncate_note(note: str, limit: int) -> str:
    return note if len(note) <= limit else note[:limit] + "\n...[truncated]"


def build_distil_prompt(run: RunArtifacts, prereqs: tuple[str, ...]) -> str:
    """The prompt that grounds the model in the real trajectory + the certifying score."""
    moves = []
    for i, (phase, entries) in enumerate(_move_sequence(run.provenance), 1):
        for entry in entries:
            query = _query_text(entry)
            suffix = f": {_truncate(query, 160)}" if query else ""
            moves.append(f"{i}. [{phase}] {entry.get('tool', '')}{suffix}")
    rel = _score_prose(_reliability(run.eval_scores))
    return (
        "Generalize this single high-scoring intelligence-analysis workup trajectory into a "
        "transferable, reusable analytic skill. An external eval certified it (the verifiable "
        f"reward): {rel}.\n\n"
        f"Capabilities used: {', '.join(prereqs)}.\n\n"
        f"## Trajectory (ordered tool calls)\n" + "\n".join(moves) + "\n\n"
        f"## Analytic note it produced\n{_truncate_note(run.note, 2000)}\n\n"
        "Write the skill as a procedure an analyst-agent could follow on a *different* entity "
        "and store: the applicability conditions, the gather -> act -> verify -> synthesize "
        "steps, the termination criteria, and the citation discipline. Generalize the specific "
        "queries into reusable moves; do not hard-code this entity's names. Submit it with the "
        "propose_skill tool."
    )


def distil_with_llm(
    run: RunArtifacts,
    *,
    call_llm: Callable[[str], dict[str, Any]],
    name: str | None = None,
    model: str = _DEFAULT_MODEL,
) -> DistilledSkill:
    """Generalize a certified trajectory into a transferable skill via an injected LLM seam.

    The model proposes the name/description/procedure prose; the structured metadata
    (prerequisites, granularity, reliability, source) is computed deterministically, never
    trusted to the model. ``name`` overrides the model's proposed slug.
    """
    certify(run)
    prereqs = prerequisites(run)
    source = _source(run)
    proposal = call_llm(build_distil_prompt(run, prereqs))
    # A forced tool-call can come back truncated (max_tokens) with the large `body` field
    # missing; fail with a clear, actionable error rather than a raw KeyError (caught live).
    required = ("description", "body") if name else ("name", "description", "body")
    missing = [k for k in required if not proposal.get(k)]
    if missing:
        raise RuntimeError(
            f"distiller returned an incomplete propose_skill call (missing/empty: "
            f"{', '.join(missing)}); the response was likely truncated — raise max_tokens or retry."
        )
    card = SkillCard(
        name=name or proposal["name"],
        description=proposal["description"],
        granularity=granularity(prereqs),
        prerequisites=prereqs,
        reliability=_reliability(run.eval_scores),
        source=source,
        distilled_by=f"llm:{model}",
    )
    return DistilledSkill(card=card, skill_md=_render_skill_md(card, proposal["body"]))


# --- writing the proposal (propose -> ratify -> freeze) ----------------------------


def write_skill(out_root: str | Path, skill: DistilledSkill) -> Path:
    """Write ``<out_root>/<name>/{SKILL.md, skill-card.toml}``; return the skill dir.

    A *draft* a human reviews and moves under ``.claude/skills/`` to ratify (where the
    existing loader auto-discovers it). The agent only proposes.
    """
    out = Path(out_root) / skill.card.name
    out.mkdir(parents=True, exist_ok=True)
    (out / "SKILL.md").write_text(skill.skill_md, encoding="utf-8")
    (out / "skill-card.toml").write_text(skill.card.to_toml(), encoding="utf-8")
    return out


# --- the live distiller (the adaptive extra; mirrors ClaudeSchemaMapper) -----------

_DISTILL_SYSTEM = (
    "You are a tradecraft engineer. You distil one successful intelligence-analysis agent "
    "trajectory into a single, transferable, reusable skill that a different agent could "
    "follow on a different entity and store. Generalize the specific moves; keep the citation "
    "discipline (every asserted fact carries a [cite:gN]). Submit it with the propose_skill tool."
)

PROPOSE_SKILL_TOOL: dict[str, Any] = {
    "name": "propose_skill",
    "description": (
        "Submit the distilled analytic skill: a kebab-case slug name, a specific auto-trigger "
        "description, and the Markdown procedure body."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "kebab-case slug, e.g. cross-store-entity-corroboration",
            },
            "description": {
                "type": "string",
                "description": "one sentence, specific enough to auto-trigger the skill",
            },
            "body": {
                "type": "string",
                "description": "Markdown: applicability, gather/act/verify/synthesize, "
                "termination, citation rule",
            },
        },
        "required": ["name", "description", "body"],
    },
}


class ClaudeSkillDistiller:
    """An LLM skill distiller backed by the Claude Messages API (the ``adaptive`` extra).

    Forces the ``propose_skill`` tool for structured output; mirrors
    :class:`ariadne.mapping.llm_mapper.ClaudeSchemaMapper` (lazy ``anthropic`` import so the
    static checker and the core package stay clean without the extra). There is no repair
    loop: a skill has no deterministic structural validator to terminate one (its gate is the
    source-run certification + human ratification, not a self-judged re-prompt).
    """

    # A skill body is prose, far longer than a mapping's structured output — 2048 (the
    # mapper's budget) truncates mid-body and drops the required `body` field (caught live).
    def __init__(self, *, model: str = _DEFAULT_MODEL, max_tokens: int = 8192) -> None:
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
            system=_DISTILL_SYSTEM,
            tools=[PROPOSE_SKILL_TOOL],
            tool_choice={"type": "tool", "name": "propose_skill"},
            messages=[{"role": "user", "content": prompt}],
        )
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == "propose_skill":
                return dict(block.input)
        raise RuntimeError("distiller did not return a propose_skill tool call")
