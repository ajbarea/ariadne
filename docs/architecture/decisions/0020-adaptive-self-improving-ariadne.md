# 0020, Adaptive & self-improving Ariadne — bounded and audited, on a propose→ratify→freeze spine

- **Status:** Accepted (2026-06-05)
- **Deciders:** Ariadne maintainers
- **Design spec:** [2026-06-05-adaptive-self-improving-ariadne-design.md](../../superpowers/specs/2026-06-05-adaptive-self-improving-ariadne-design.md)

## Context

Ariadne generalizes at **code level** today: a new corpus needs a hand-written
`DatasetAdapter` mapped into the canonical schema and registered in `DATASETS`
([ADR-0006](0006-dataset-agnostic-pipeline.md)). To be a general sensemaking harness
it needs to (a) **adapt at runtime** to a user's own store/ontology and (b) **improve
from experience** across repeated workups — *without* eroding the auditable,
read-only, no-silent-merge, provenance-by-hook governance that is the project's whole
value to an intelligence-analysis stakeholder. The trigger was a direct ask: make the
dynamic Ariadne "as recursively self-improving as possible."

## Decision drivers

- **Governance is non-negotiable.** Any adaptive/learned change must remain
  auditable and must not let the system silently alter what it is graded against.
- **Anthropic's RSI framing.** Recursive self-improvement is the *unbounded* form
  (an AI autonomously designing its successor); the remaining — and explicitly
  human — bottleneck is *judgment, verification, and direction*. We build the
  bounded form that keeps those human.
- **2026 self-improvement practice.** The deployable pattern is skill libraries +
  procedural memory + reflexion + *audited* skill-graph improvement with verifiable
  rewards — every serious source warns that deployed self-improvement invites
  reward-hacking and untraceable drift unless "design rules and tests govern what
  changes are allowed."
- **Build on what exists.** Ariadne already has the canonical-schema seam, MCP tool
  families, integration ports, and — crucially — a verifiable reward (the eval
  harness) and an audit trail (provenance + governance audit).

## Considered options

1. **Fully autonomous adaptation (LLM rewrites mappings/tools/code at runtime).**
   *Rejected.* This is the unbounded RSI form. It maximises "magic" but destroys
   auditability and invites reward-hacking (an agent that can edit its grader will
   game it). Disqualified by the governance spine.
2. **Stay code-only (status quo: hand-written adapters).** *Rejected as the end
   state.* Safe and auditable but not a general harness; every new corpus needs the
   maintainer. Keep it as the *fallback*, not the only path.
3. **Bounded, audited adaptation on a propose→ratify→freeze spine.** *Chosen.* The
   agent *proposes* declarative artifacts (schema mappings, ontologies, named
   skills); a human *ratifies*; the artifact is *frozen* as config the deterministic
   gates keep checking. Self-improvement edits only those declarative, ratified
   artifacts — never the gates, scorers, governance, or code.

## Decision

Adopt **option 3**. Architecturally, two axes ride the one spine:

- **Axis A — Adaptivity:** schema introspection (A1), a declarative user
  ontology/semantic layer (A2), dynamic MCP tool registration (A3).
- **Axis B — Self-improvement (bounded, audited):** learned mappings as procedural
  memory (B1), learned analytic skills (B2), reflexion over the eval harness (B3).

**The hard boundary (the safety architecture):** the self-improvement loop edits
*only* declarative, ratified artifacts. It **never** edits its own gates, eval
scorers, governance rules, or code. The gates and the human ratification step are
fixed points. This single rule is what makes the loop defensible.

**Sequencing.** First slice = A1 + A2-into-the-existing-canonical-schema + the B1
seed, on **Postgres**: introspect a real Postgres, the agent proposes a mapping into
`person/org/site/document` + edges, a human ratifies, it freezes as `mapping.toml`,
and the existing indexer/workup/eval run unchanged on the user's data. The full user
ontology (A2), dynamic MCP (A3), learned skills (B2), and reflexion (B3) are later,
separately-specced phases. Store target is Postgres first (richest standardized
introspection, most mature agentic schema-linking research, reuses postgres-mcp
restricted mode); ontology format is a lightweight declarative TOML, SHACL-validatable
later.

## Consequences

- Ariadne moves from code-extensible toward runtime-adaptive **and** experience-
  improving, while every change stays auditable and human-ratified — the governance
  spine is preserved, not bypassed.
- The eval harness and provenance audit are repurposed as the reward signal and
  audit trail for a self-improvement loop, a differentiated position most agents
  cannot claim.
- The first slice is small and reversible (read-only introspection + a ratified
  config + the existing pipeline); the larger vision is phased behind it, not
  front-loaded (YAGNI).
- A clear, statable safety boundary (no self-editing of gates/scorers/code) makes
  the capability presentable to an intelligence-analysis stakeholder.

Sources: Anthropic, *Recursive self-improvement*
([anthropic.com/institute/recursive-self-improvement](https://www.anthropic.com/institute/recursive-self-improvement));
audited skill-graph self-improvement with verifiable rewards
([arXiv 2512.23760](https://arxiv.org/pdf/2512.23760)); procedural memory from
experience ([ProcMEM, arXiv 2602.01869](https://arxiv.org/pdf/2602.01869)); Voyager
skill libraries; AutoLink agentic schema linking
([arXiv 2511.17190](https://arxiv.org/pdf/2511.17190)); OntoKG intrinsic-relational
routing ([arXiv 2604.02618](https://arxiv.org/html/2604.02618v1)); Anchor
schema-agnostic KG construction ([arXiv 2606.01208](https://arxiv.org/html/2606.01208v1));
dynamic MCP ([dynamic-fastmcp](https://github.com/ragieai/dynamic-fastmcp),
[Docker Dynamic MCP](https://docs.docker.com/ai/mcp-catalog-and-toolkit/dynamic-mcp/)).
