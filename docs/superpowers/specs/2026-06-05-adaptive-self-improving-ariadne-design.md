# Adaptive & self-improving Ariadne — design

- **Date:** 2026-06-05
- **Status:** Approved design (implementation phased; first slice specced below)
- **Decision record:** [ADR-0020](../../architecture/decisions/0020-adaptive-self-improving-ariadne.md)

## Problem

Ariadne generalizes today at **code level**: to analyze a new corpus, a developer
writes a `DatasetAdapter`, maps the source into the canonical schema, and registers
it in `DATASETS` ([ADR-0006](../../architecture/decisions/0006-dataset-agnostic-pipeline.md)).
That is powerful but it means *the maintainer* extends Ariadne. Two capabilities are
missing for the tool to be a general sensemaking harness:

1. **Runtime adaptivity** — a user points Ariadne at *their* store (schema, ontology,
   vocabulary) and it adapts without a code change.
2. **Experience improvement** — Ariadne gets better at a user's data over repeated
   workups: it remembers what worked and proposes refinements, rather than starting
   cold each time.

The hard constraint: neither capability may erode Ariadne's spine — **auditable,
read-only, no-silent-merge, provenance-by-hook** governance. A system that silently
rewrites its own mappings, tools, or gates is exactly what an intelligence-analysis
stakeholder cannot trust.

## The organizing principle: propose → ratify → freeze

Every adaptive or learned change follows one lifecycle:

1. **Propose** — the agent introspects/learns and emits a *declarative artifact*
   (a schema mapping, an ontology, a named skill) as a proposal, with provenance.
2. **Ratify** — a human reviews and accepts (or edits) the proposal. Nothing
   un-ratified is used in a scored/governed workup.
3. **Freeze** — the ratified artifact is persisted as config and becomes a fixed
   input the deterministic gates check against on every subsequent run.

This is the local, app-level form of the human/AI division Anthropic names for
recursive self-improvement (humans keep *judgment, verification, direction*; the AI
executes), and it answers the 2026 self-improvement literature's core warning
(deployed self-improvement invites reward-hacking and untraceable drift unless
"design rules and tests govern what changes are allowed").

## Two axes

### Axis A — Adaptivity (adapt to a user's data)

- **A1 · Schema introspection.** A generic connector introspects an arbitrary store
  (`information_schema` for Postgres; later `db.schema` for Neo4j; headers for CSV).
  The agent does *iterative schema linking* — retrieve only the relevant
  tables/columns rather than dumping the whole schema — with a self-correcting query
  loop. (AutoLink-style; scales past whole-schema prompting.)
- **A2 · Ontology / semantic layer.** A declarative, human-readable config (TOML)
  naming the user's entity types and relationship vocabulary, plus an LLM-assisted
  mapping from their raw schema into it. Uses OntoKG's *intrinsic-vs-relational*
  routing — each property is either a node attribute or a traversable edge (the same
  distinction the node-drawer already renders). Designed so a SHACL validator can
  wrap the same model later (Anchor-style) without redesign.
- **A3 · Dynamic MCP surface.** The MCP server registers per-source tool families
  (`mcp__relational__*`, `mcp__graph__*`) at runtime as datasets connect, emitting
  `notifications/tools/list_changed`; the lead agent routes by the discovered
  surface. (Standard 2026 MCP: dynamic-fastmcp / Spring AI / Docker Dynamic MCP.)

### Axis B — Self-improvement (improve from experience), bounded and audited

- **B1 · Learned mappings (procedural memory).** A ratified schema mapping is
  persisted; the next workup on that store reuses it instead of re-introspecting.
  This is the first concrete bite of self-improvement and is *seeded directly by
  A1+A2*.
- **B2 · Learned analytic skills.** Distil high-scoring workup trajectories into
  named, reusable, composable skills (e.g. "cross-store employer-tie check"),
  discovered and composed in later workups (Voyager / ProcMEM skill-library pattern).
- **B3 · Reflexion over eval.** The agent reflects on its *own* low-scoring eval
  dimensions (the harness already produces a trustworthy gradient: recall /
  grounded / supporting-fact F1 / reconciliation / context-utilization / ICD-203
  rubric — now surfaced in the report) and proposes a refined skill/mapping/query.

**Why Ariadne is unusually well-positioned:** audited self-improvement needs a
*verifiable reward* and an *audit trail*. Ariadne already has both — the eval
harness is the reward signal; provenance-by-hook + the read-only governance audit
is the trail. Most agents attempting self-improvement lack either.

## The hard boundary (safety architecture)

The self-improvement loop edits **only declarative, ratified artifacts** (mappings,
skills, ontology). It **never** edits its own gates, governance rules, eval scorers,
or code. An agent that can edit its own grader will learn to game it; keeping the
gates and human ratification as fixed points is what makes the loop defensible. This
is the non-negotiable line, recorded in ADR-0020.

## First slice (the increment to build next)

**Goal:** point Ariadne at a real Postgres the maintainer did *not* hand-write an
adapter for, and run a grounded workup over it — via an introspected, human-ratified,
frozen mapping into the *existing* canonical schema.

Scope (deliberately minimal — A1 + A2-into-existing-schema + B1 seed; **no** custom
user ontology yet, **no** dynamic MCP yet):

1. **Introspection** — a read-only `information_schema` reader producing a structured
   schema summary (tables, columns, types, foreign keys). Reuses the postgres-mcp
   restricted-mode posture ([ADR-0003](../../architecture/decisions/0003-postgres-mcp-restricted-mode.md)).
2. **Proposed mapping** — an injected mapper (Protocol; hermetic fake + real Claude
   behind an extra, mirroring the rubric judge) emits a candidate mapping: which
   tables→entity types, which columns→attributes (intrinsic) vs which FKs→edges
   (relational), into the canonical `person/org/site/document` + edge schema.
3. **Ratify + freeze** — the proposal is written as `mapping.toml`; a human edits/
   accepts; a deterministic validator checks **structural integrity** before it is
   usable. The canonical schema's `type` is an open string (it deliberately avoids a
   "god model"), so the validator checks structure, not a closed type list: every
   mapped column exists in the introspected summary, each entity declares an `id` +
   `name` column, and every relationship's endpoint tables are themselves mapped to
   entities (the loadability check the 2026 schema-mapping work flags — entities that
   "look right" but can't be loaded because an edge endpoint is unmapped).
4. **Apply** — a frozen `mapping.toml` drives a `DatasetAdapter` over the live
   Postgres, so the *existing* indexer + workup + eval run unchanged on the user's
   data.

Out of scope for the first slice (later phases): user-defined ontologies (A2 full),
dynamic MCP registration (A3), learned skills (B2), reflexion (B3), SHACL validation,
Neo4j/CSV introspection.

## Components & isolation

| Unit | Responsibility | Depends on |
| --- | --- | --- |
| `introspect/postgres.py` | read-only schema summary from `information_schema` | psycopg (read-only) |
| `mapping/propose.py` | `SchemaMapper` Protocol → candidate mapping (fake + Claude) | injected judge/model |
| `mapping/schema.py` | the `mapping.toml` model + deterministic validator | canonical schema |
| `mapping/adapter.py` | a `DatasetAdapter` driven by a frozen `mapping.toml` | ADR-0006 seam |

Each is independently testable; the mapper is injectable so the engine stays pure
and hermetic.

## Testing

- Pure introspection over a fixture `information_schema` dump (no live DB) +
  one live integration test (testcontainers Postgres) behind the `integration` marker.
- Mapper engine tested with a hermetic fake `SchemaMapper`; the real Claude mapper
  behind an extra + a `network`/`integration` test.
- Validator: golden + adversarial mappings (column not in the introspected schema,
  relationship endpoint table unmapped, entity missing its id/name column).
- A frozen-`mapping.toml` → adapter → indexer → workup → `eval` round-trip on a small
  seeded Postgres, asserting a grounded note (the propose→ratify→freeze loop end to
  end).

## Risks & mitigations

- **Mapping is wrong/misleading** → human ratify gate + deterministic validator;
  never auto-applied.
- **Scope creep into full ontology engine** → first slice maps into the *existing*
  schema only; ontology is a later, separately-specced phase.
- **Self-improvement drift / reward-hacking** → the hard boundary (loop never edits
  gates/scorers/code); every learned artifact is ratified and gate-checked.
- **Read/write safety on a user's DB** → introspection and queries are read-only
  (restricted mode), audited by the existing governance pass.
