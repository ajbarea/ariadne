# Ariadne — Phase 1 design: single-store vertical slice

> **Status:** design, awaiting review. Authored 2026-06-01.
> **Scope decision (AJ, 2026-06-01):** *Full live harness + real Neo4j* — the CLI
> runs the real Claude Agent SDK agent loop against a real Neo4j backend.
> **Source research:** [`docs/research/best-practice-architecture.md`](../../research/best-practice-architecture.md),
> [`docs/research/claude-agent-sdk-reference.md`](../../research/claude-agent-sdk-reference.md),
> plus the June-2026 connector/Text2Cypher pass recorded inline below.

## Goal

Prove the harness end-to-end on **one store**: input a target **entity or
organizational node**, traverse its organizational relationships in a graph DB
through a coordinated tool sequence, and synthesize a **cited analytic note** —
with every surfaced fact traceable to the tool call that sourced it. This is the
minimum that demonstrates success criteria (1) traverse, (3) reduce pivot burden,
and seeds (4) non-obvious connections; full multi-modal reconciliation (2) is
Phase 3.

## Decisions (research-grounded)

### D1 — Graph connector = official `mcp-neo4j-cypher` server (stdio, read-only)

`# research(2026-06):` Provenance does **not** require an in-process server — the
SDK's `PostToolUse` hook matches by **tool name** and is transport-agnostic, so it
fires on an external server's tools too. The production guardrails the brief
demands (governance: read-only enforcement, query timeouts, row limits,
token-aware truncation, injection-safe parameterization) are already implemented
in the official Neo4j MCP server; rolling our own in-process wrapper would
re-implement security-critical code (YAGNI + risk). Configure read-only via
`NEO4J_READ_ONLY=true`. The Google `genai-toolbox` `neo4j-cypher` tool and
`mcp-neo4j-cypher` are the reference implementations.
Sources: [Neo4j MCP](https://pypi.org/project/mcp-neo4j-cypher/),
[controlled MCP responses](https://towardsdatascience.com/preventing-context-overload-controlled-neo4j-mcp-cypher-responses-for-llms/),
[Text2Cypher guide](https://medium.com/neo4j/text2cypher-guide-cc161518a509).
*Phase-2 swap point:* a different graph backend behind the same MCP tool family.

### D2 — Agent writes read-only Cypher; no separate Text2Cypher tool in Phase 1

`# research(2026-06):` The Feb-2026 Neo4j complexity–frequency matrix recommends
**dedicated parameterized tools for frequent/complex queries** and **agentic
(LLM-written) Cypher for exploratory/low-frequency** scenarios. A Phase-1 entity
workup is exploratory/low-frequency → the agent reads schema, then writes
read-only Cypher. Promote hot traversals (e.g. `REPORTS_TO` chains) to dedicated
parameterized tools in Phase 2 if they prove frequent.
Source: [Text2Cypher guide](https://medium.com/neo4j/text2cypher-guide-cc161518a509).

### D3 — Live agent loop is the deliverable; deterministic pieces are hermetic

The CLI runs the real agent loop (needs `ANTHROPIC_API_KEY`). Everything we own
that is *not* the LLM call (provenance hook, citation-coverage validator, note
assembly, CLI option assembly) is unit-tested hermetically with recorded MCP
tool-response fixtures. The live end-to-end run is an integration test that skips
when no key is present.

### D4 — Kuzu rejected as embedded backend

`# research(2026-06):` Kuzu (the natural embedded Cypher option) was **archived by
its sponsor in Oct 2025**; only community forks (RyuGraph, bighorn) remain. Not
pinned. Neo4j is the production graph standard.
Source: [The Register](https://www.theregister.com/2025/10/14/kuzudb_abandoned/).

## Architecture

```
ariadne workup <entity>
   │
   ├─ ClaudeAgentOptions(
   │     mcp_servers   = { neo4j: stdio(mcp-neo4j-cypher, READ_ONLY) },
   │     hooks         = { PostToolUse: [provenance] },
   │     allowed_tools = ["mcp__neo4j__*"],
   │     system_prompt / skill = entity-workup )
   │
   ├─ agent loop:  gather (schema → locate entity → expand hierarchy)
   │               → act (read-only Cypher for relationships)
   │               → verify (cross-check + citation coverage)
   │               → synthesize (cited analytic note from template)
   │
   └─ outputs:  <out>/note.md         (cited analytic note)
                <out>/provenance.jsonl (audit ledger; one line per graph tool call)
```

The PostToolUse provenance hook fires on every `mcp__neo4j__*` result, regardless
of the fact that the connector is an external stdio subprocess.

## Components

Each unit is independently testable; interfaces are explicit.

| Unit | Path | Responsibility | Depends on |
| ---- | ---- | -------------- | ---------- |
| **provenance hook** | `src/ariadne/hooks/provenance.py` | `PostToolUse` callback: append `(ts, tool, args, citation_keys)` to a run ledger; expose the ledger object | SDK hook types only |
| **citation keys** | `src/ariadne/provenance/citations.py` | derive stable citation keys from a Neo4j result (node element-ids / query hash); format `[cite:KEY]` | — (pure) |
| **citation validator** | `src/ariadne/provenance/validate.py` | every `[cite:KEY]` in the note resolves to a ledger entry; report uncited claims / dangling cites | ledger + note (pure) |
| **note assembly** | `src/ariadne/report/note.py` | render the analytic-note template; write `note.md` + `provenance.jsonl` to `--out` | — (pure I/O) |
| **graph MCP config** | `src/ariadne/graph/neo4j_server.py` | build the stdio `McpServerConfig` for `mcp-neo4j-cypher` (URI/user/password/read-only/timeout/limits from env) | env |
| **entity-workup skill** | `.claude/skills/entity-workup/SKILL.md` (+ `note-template.md`) | the gather→act→verify→synthesize workflow body; auto-triggers on "run entity workup on …" | (content) |
| **CLI** | `src/ariadne/cli.py` + `__main__.py` | parse `workup <entity> [--graph neo4j] [--format md\|json] [--out DIR]`; assemble `ClaudeAgentOptions`; run `query()`; persist outputs; clear error when key/Neo4j absent | all above |
| **seed dataset** | `infra/neo4j/seed.cypher` + `docker-compose.yml` | synthetic, fictional org hierarchy with one non-obvious multi-hop link | — |

### Graph tools used (from the official server)
`mcp__neo4j__get_neo4j_schema` (introspection) and `mcp__neo4j__read_neo4j_cypher`
(read-only Cypher). Write tools disabled by read-only mode. Exact tool names are
verified against the installed server at implementation time.

### Seed dataset (synthetic, fictional)
Nodes: `Unit`, `Person`, `Role`. Edges: `REPORTS_TO`, `MEMBER_OF`, `CO_LOCATED`,
`COMMUNICATES_WITH`. Includes a deliberately **non-obvious multi-hop connection**
(e.g. two persons linked only via a shared co-located unit three hops up the
hierarchy) so the demo exercises success-criterion (4). Clearly fictional names;
no real-world entities.

## Data flow & citation contract

1. Agent calls `get_neo4j_schema` then `read_neo4j_cypher`.
2. PostToolUse hook records each call + derives citation keys from returned nodes.
3. The skill instructs the agent to attach `[cite:KEY]` to every asserted fact.
4. On completion the CLI runs the citation validator: the note passes only if
   every `[cite:KEY]` resolves to a ledger entry (a concrete first answer to the
   brief's *"how do you know it works?"*). Validation result is written alongside.

## Error handling

- **No `ANTHROPIC_API_KEY`** → CLI exits non-zero with a one-line "export
  ANTHROPIC_API_KEY" message (no partial run).
- **Neo4j unreachable** → surfaced from the `system:init` MCP-connection status;
  CLI exits with a "start Neo4j (`docker compose up neo4j`)" message.
- **Citation validation fails** → note is still written, but the CLI exits
  non-zero and prints the uncited claims / dangling cites (governance gate).
- **Tool/query error mid-run** → the agent sees the failure (SDK does not
  auto-retry) and may revise; the hook logs the failed call.

## Dependencies (pinned with `# research(2026-06)` notes in pyproject)

- **runtime:** `claude-agent-sdk` (harness), `neo4j` (driver — seeding + health
  checks + integration), `mcp-neo4j-cypher` (the connector server).
- **dev:** `testcontainers[neo4j]` (integration Neo4j).

## Testing strategy

- **Unit (hermetic; no key, no Docker):** provenance hook against recorded
  `mcp__neo4j__*` tool-result fixtures; citation-key derivation; citation
  validator (pass + both failure modes); note assembly/output; CLI arg parsing +
  `ClaudeAgentOptions` assembly (agent run mocked); skill frontmatter parses.
- **Integration (`-m integration`):** testcontainers Neo4j seeded from
  `seed.cypher`; the official server launched read-only; a live agent `workup`
  run **behind a key check** (skips if `ANTHROPIC_API_KEY` unset) asserting a
  cited note + non-empty ledger + passing citation coverage, including surfacing
  the planted non-obvious multi-hop link.

## Out of scope (later phases)

SQL + vector connectors and source-routing (Phase 2); multimodal-to-text
(Phase 3); confidence scoring, eval harness for all four success criteria,
sibling-tool interfaces (Phase 4); air-gapped fork (Phase 5); dedicated
parameterized graph tools (Phase 2 if traversals prove hot).

## Success criteria for Phase 1 (done = all true)

1. `ariadne workup <entity>` against the seeded Neo4j produces `note.md` citing
   real graph facts + a `provenance.jsonl` ledger.
2. Citation coverage validates (every claim cites a ledger entry).
3. The note surfaces the planted non-obvious multi-hop connection.
4. `make lint` + `make test-unit` green locally; integration test green with a key.
</content>
</invoke>
