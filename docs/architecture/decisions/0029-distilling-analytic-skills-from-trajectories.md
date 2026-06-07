# 0029, Distilling analytic skills from eval-certified trajectories — `ariadne distil`

- **Status:** Accepted (2026-06-07)
- **Deciders:** Ariadne maintainers
- **Refines:** [ADR-0020](0020-adaptive-self-improving-ariadne.md) (axis B2, learned analytic
  skills) · builds on [ADR-0019](0019-retrieval-side-evaluation-for-sensemaking.md) +
  [ADR-0024](0024-trajectory-grades-observations.md) (the eval harness as verifiable reward)
  and the seed `entity-workup` SKILL.md

## Context

Axis B is **bounded, audited self-improvement**. B2 is *learned analytic skills*: distil a
high-scoring workup trajectory into a named, reusable, declarative skill the harness
auto-discovers on the next workup. The raw material already exists per run —
`provenance.jsonl` (the trajectory: the ordered, cited tool calls), `eval.json` (the
scores), `note.md` (the synthesis). The contestable questions: (1) **an eager, persisted
library vs ephemeral test-time synthesis**; (2) **what certifies a trajectory worth learning
from** — the keystone governance question, because a loop that learns from its own ungrounded
output reward-hacks itself; (3) **flat prose vs a structured skill store**. Hence this ADR.

## Decision drivers

- **The propose → ratify → freeze spine + the hard boundary ([ADR-0020](0020-adaptive-self-improving-ariadne.md)).**
  A learned skill is a declarative artifact the agent *proposes*, a human *ratifies*, and that
  *freezes* as a `SKILL.md` the deterministic harness reads. The loop never edits its gates,
  scorers, governance, or code.
- **Self-improvement is reliable only against an external verifiable reward.** 2026 practice
  (SkillGen) marks a synthesized skill "active" only when a verifier shows net gain — "explicit
  validation of skill effects, rather than assuming quality, is essential." Ariadne already
  *owns* that verifier: the eval harness ([ADR-0019](0019-retrieval-side-evaluation-for-sensemaking.md)).
  Intrinsic self-judgment is not a gate (the model that erred shares the blind spot).
- **A structured skill store, not a flat cache.** SoK Agentic Skills: a skill packages
  procedural knowledge with explicit *applicability conditions, execution policy, termination
  criteria, and a reusable interface*; the store records *granularity / prerequisites /
  reliability*. A bare prose blob is a flat cache that fails on every one of those axes.
- **Auditability / the citation ethos.** A distilled skill must cite the specific trajectory
  *and* score it came from — the same provenance discipline the analytic notes carry.
- **Architectural consistency with A1.** `ariadne map` is already propose → ratify → freeze
  with a deterministic baseline + an `--llm` agentic proposer behind a validator
  ([ADR-0025](0025-applying-a-ratified-mapping.md)/[ADR-0026](0026-llm-schema-mapper.md)). B2 is
  the skill-shaped analog; reuse the shape rather than invent a second one.

## Considered options

1. **Test-time skill synthesis (SkillTTA / "Skills on the Fly"): synthesize an ephemeral,
   task-specific skill during a workup, never persisted.** *Rejected as the B2 mechanism.* It
   bypasses ratification — an unratified artifact enters the loop — breaching
   [ADR-0020](0020-adaptive-self-improving-ariadne.md)'s spine. (Legitimate as a *future*
   inference-time aid, gated behind the same eval, but not the durable learned-skill path.)
2. **Distil from any completed run.** *Rejected.* A run that scored `grounded=false` grounded
   nothing; distilling a "skill" from it teaches the loop its own hallucination — the textbook
   reward-hack. There must be a certification gate.
3. **Emit a single prose `SKILL.md`, no structured metadata.** *Rejected.* A flat cache: not
   queryable by prerequisites/reliability, no auditable provenance of the skill's *own* quality
   — fails the SoK structured-store bar.
4. **`ariadne distil <run>`: distil an eval-*certified* trajectory into a structured,
   declarative skill (`SKILL.md` + a `skill-card.toml` sidecar), proposed into a staging dir for
   human ratification; deterministic by default, `--llm` to generalize.** *Chosen.*

## Decision

Adopt **option 4**, in a new `learning/` package (`src/ariadne/learning/distil.py`) plus an
`ariadne distil` command.

- **The certification gate (the keystone).** `distil` reads the run's `eval.json` and refuses
  unless the run was scored **and** `grounded is true`. No eval ⇒ no external verifiable reward
  ⇒ no distillation (the honest capability line). The eval harness — the same deterministic gate
  the loop may never edit — is what certifies a trajectory worth learning from. The full score
  vector (recall, trajectory, supporting-fact F1, citation coverage, …) is recorded as the
  skill's **reliability** for the human ratifier to weigh; `grounded` is the binary admission gate.
- **The structured skill (SoK).** Output is a skill directory: a `SKILL.md` (spec-clean
  frontmatter `name`/`description` for auto-discovery + a body stating the procedure, the
  termination/interface, and a `## Provenance` footer citing the source run + score) **and** a
  sidecar **`skill-card.toml`** — the machine-readable store record: `granularity` (atomic vs
  composite, by store count), `prerequisites` (the tool families the trajectory used),
  `reliability` (the eval scores), `source` (run id / dataset / entity / git sha / fixture),
  `distilled_by`. Prose for the agent, structure for the store — the `note.md`/`eval.json` split.
- **Deterministic baseline + `--llm` (mirror A1).** The deterministic distiller *records*: it
  groups the trajectory into tool-family phases (graph-schema / relational-schema / graph
  traversal / relational query / free-text evidence) and writes a faithful procedure skeleton —
  it cannot generalize (the honest line, as `BaselineMapper` cannot invent a vocabulary).
  `--llm` runs the Trace2Skill move: a Claude model generalizes the trajectory + note into
  transferable procedural prose via **forced tool-use** (`propose_skill`), behind the `adaptive`
  extra + a key-guard, reusing the `call_llm` seam and lazy-`anthropic` pattern of
  `ClaudeSchemaMapper`.
- **Propose → ratify → freeze.** `distil` writes to `skills-proposed/<name>/` (a draft,
  gitignored). A human reviews and moves it under `.claude/skills/<name>/`, where the existing
  loader auto-discovers it. Ratification is where a human (later, automatably) runs the
  SkillGen-style **net-effect** check — does a workup *using* the skill out-score one without it
  — before freezing. The agent only proposes.

## Consequences

- Ariadne gains the B2 learned-skill path: a certified-good workup becomes a named, structured,
  auditable skill that can improve the next workup — without the agent ever self-onboarding an
  unvetted artifact or editing a gate.
- **The eval harness is now load-bearing twice**: as the reward signal
  ([ADR-0019](0019-retrieval-side-evaluation-for-sensemaking.md)) *and* the admission gate for
  learning. This couples B2 to the same verifiable reward B3's reflexion will use, and is the
  concrete answer to "how do you stop self-improvement gaming itself": you only learn from what
  the gate you cannot edit has already certified.
- The skill carries its own provenance + reliability, so a ratifier sees the basis (which run,
  which scores) inline — the citation ethos extended from notes to skills. Security framing: a
  ratified skill is an injected instruction; the ratify step is its trust boundary (Secure Agent
  Skills threat model).
- Honest scoping (YAGNI): the first slice distils from **one** trajectory. Trace2Skill's
  multi-trajectory hierarchical consolidation, skill *composition* (`composes_with`), deepening
  an existing skill, and the automated net-effect ratification check are deferred — named here,
  not built. Test-time synthesis (option 1) is a separate future track.

Sources: Trace2Skill — trajectory-local lessons → transferable declarative skills, a conflict-free
skill directory ([arXiv 2603.25158](https://arxiv.org/abs/2603.25158)); Skills on the Fly /
SkillTTA — ephemeral test-time synthesis ([arXiv 2605.16986](https://arxiv.org/abs/2605.16986));
SkillGen — a verifier gate keeps a skill only on net gain
([arXiv 2605.10999](https://arxiv.org/html/2605.10999)); SoK: Agentic Skills — applicability /
policy / termination / interface + structured store ([arXiv 2602.20867](https://arxiv.org/html/2602.20867v1));
Towards Secure Agent Skills — a skill is injected instruction; ratification is its trust boundary
([arXiv 2604.02837](https://arxiv.org/html/2604.02837v1)); Agent Skills `SKILL.md` format
([Anthropic Agent Skills](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview)).
