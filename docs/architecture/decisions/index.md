# Decision log

Architectural decisions for Ariadne, recorded as **ADRs** (Architecture Decision
Records) in the [MADR](https://adr.github.io/madr/) format. One file per decision.
This is the single place to point to when someone asks *"why did you choose X
instead of Y?"*, each record names the alternatives that were considered, why
they lost, and what the choice costs us.

## Why we keep these

Decisions get made constantly and then disappear into chat logs and commit
messages. An ADR is a small, dated, immutable record of one decision and its
*rejected* alternatives, kept in source control next to the code so it stays in
sync. When the context changes, we don't edit the old record, we supersede it
with a new one.

## When to write one

Write an ADR when a choice is **architecturally significant and contestable**: a
store, a framework, a connector, a security posture, a deferral. Skip it for
reversible implementation details. A good trigger is *"a reviewer could
reasonably ask why we didn't do it the other way."* Each design choice should
still carry its `# research(YYYY-MM):` provenance at the code/roadmap level; the
ADR is where the *comparison* lives.

## The records

| # | Decision | Status |
| - | -------- | ------ |
| [0001](0001-orchestration-on-claude-agent-sdk.md) | Orchestrate on the Claude Agent SDK | Accepted |
| [0002](0002-official-mcp-connectors-over-hand-rolled.md) | Use official MCP connectors over hand-rolled wrappers | Accepted |
| [0003](0003-postgres-mcp-restricted-mode.md) | Expose Postgres via `postgres-mcp` Restricted Mode | Accepted |
| [0004](0004-postgres-over-redis-for-relational-store.md) | Keep Postgres (not Redis) for the relational store | Accepted |
| [0005](0005-defer-subagent-fan-out.md) | Defer subagent fan-out pending a design pass | Deferred |
| [0006](0006-dataset-agnostic-pipeline.md) | Dataset-agnostic pipeline (canonical schema + adapters) | Accepted |
| [0007](0007-hybrid-retrieval-fulltext-first.md) | Hybrid retrieval, full-text first (in-Postgres) | Accepted |
| [0008](0008-multimodal-agentic-to-text-not-native-embeddings.md) | Multimodal via agentic-to-text, not native multimodal embeddings | Accepted |
| [0009](0009-distribute-as-mcp-server-and-plugin.md) | Distribute as an MCP server, wrapped in a Claude Code plugin | Accepted |
| [0010](0010-observability-opentelemetry.md) | Observability via OpenTelemetry (GenAI conventions) | Accepted |
| [0011](0011-llm-rubric-analytic-standards-eval.md) | LLM-rubric scoring of analytic standards (ICD-203) | Accepted |
| [0012](0012-cloud-vs-air-gapped-deployment-fork.md) | Cloud vs. air-gapped deployment fork (single seam) | Accepted |
| [0013](0013-user-selectable-model-profiles.md) | User-selectable model profiles (curated allowlist) | Accepted |
| [0014](0014-pgvector-for-the-semantic-leg.md) | pgvector for the semantic-leg vector store | Accepted |
| [0015](0015-subagent-fan-out-design.md) | Subagent fan-out — design specified, implementation gated | Accepted |
| [0016](0016-entity-resolution-across-stores.md) | Entity resolution across stores — tiered, ingestion-first | Accepted |
| [0017](0017-interactive-workup-report.md) | Results presentation — self-contained interactive workup report | Accepted |
| [0018](0018-multimodal-connector-slate.md) | Multimodal connector slate — text/audio/relational shipped, video deferred | Accepted |
| [0019](0019-retrieval-side-evaluation-for-sensemaking.md) | Retrieval-side evaluation — context utilization, not precision@k | Accepted |
| [0020](0020-adaptive-self-improving-ariadne.md) | Adaptive & self-improving Ariadne — bounded, audited, propose→ratify→freeze | Accepted |
| [0021](0021-run-output-organization.md) | Run-output organization — immutable per-run dirs + reproducibility manifest | Accepted |
| [0022](0022-citation-recall-coverage-hardening.md) | Citation-recall coverage hardening — P-Cite repair loop + abbreviation-robust segmentation | Accepted |
| [0023](0023-measuring-citation-coverage-gain.md) | Measure the P-Cite repair loop's citation-coverage gain (Δcoverage) | Accepted |
| [0024](0024-trajectory-grades-observations.md) | Trajectory eval grades observations, not just actions | Accepted |
| [0025](0025-applying-a-ratified-mapping.md) | Apply a ratified mapping — it self-registers as a dataset | Accepted |
| [0026](0026-llm-schema-mapper.md) | LLM-backed schema mapper — forced tool-use + validator-terminated retry | Accepted |
| [0027](0027-declarative-user-ontology.md) | Declarative user ontology — a lightweight TOML vocabulary the mapper maps into | Accepted |
| [0028](0028-runtime-dataset-activation-over-mcp.md) | Runtime dataset activation over MCP — `connect_dataset` + a dynamically-registered tool | Accepted |

## Template

New records follow the MADR shape: **Context → Decision drivers → Considered
options (with pros/cons) → Decision → Consequences**, plus a one-line status and
the sources behind the call. Copy an existing record and keep it to a single
decision.
