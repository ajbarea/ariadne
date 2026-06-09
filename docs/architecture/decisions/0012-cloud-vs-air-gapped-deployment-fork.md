# 0012, Cloud vs. air-gapped deployment fork

- **Status:** Accepted (2026-06-04)
- **Deciders:** Ariadne maintainers
- **Relates to:** [ADR-0001](0001-orchestration-on-claude-agent-sdk.md) (the Claude Agent SDK is the harness that forks at the model boundary), [ADR-0007](0007-hybrid-retrieval-fulltext-first.md) + [ADR-0008](0008-multimodal-agentic-to-text-not-native-embeddings.md) (local-first retrieval/embedding choices that pre-empt the classic air-gap leak), [ADR-0010](0010-observability-opentelemetry.md) (OTLP exports to an on-prem backend)

## Context

The brief constrains deployment to **hybrid**: Ariadne must run both cloud-first
(frontier Claude) and on-prem / **air-gapped** (self-hosted, open-weight, no
egress). The open question has been: where does the architecture actually fork,
and how much of Ariadne has to change to cross the gap?

`# research(2026-06):` Air-gapped is an *architecture*, not a config flag: every
runtime dependency must be pre-staged inside the enclave (local model registry
with signed import, local inference workers, local vector DB + local embedding,
container/package mirrors, on-prem observability, internal PKI), and the **egress
surface is a first-class concern**: ideally the empty set, enforced by a network
policy and a CI check that fails on any new outbound dependency. The single most
common real-world leak is the **embedding step**: an SDK that defaults to a cloud
embedding API, caught only when network monitoring shows DNS to `api.openai.com`
from a "air-gapped" pipeline.

## Decision drivers

- **Minimise the fork surface**: the fewer components that differ between cloud
  and air-gapped, the less there is to validate and keep in sync.
- **No silent egress**: every component must have an in-enclave substitution
  with no hidden call-home (the embedding-leak failure mode).
- **No fork in the analytic logic**: the harness, gates, provenance, and eval
  must be identical across both deployments; only infrastructure swaps.

## Considered options

### A. Single-seam fork at the orchestrator model (chosen)

Keep one codebase. Everything except the orchestrator LLM is already in-enclave
or trivially self-hostable; the model forks at the `ANTHROPIC_BASE_URL` boundary.

- **Pros:**
  - The Claude Agent SDK is **not** a cloud lock-in: point `ANTHROPIC_BASE_URL`
    at a **LiteLLM proxy** that translates the Anthropic Messages API to
    OpenAI-format and forwards to a local **vLLM / TGI / Ollama** worker serving
    an open-weight tool-use model. The agent loop, tools, skills, hooks, and
    provenance are byte-identical, only an env var changes.
  - Ariadne's retrieval/eval layers are **already air-gap-clean by prior
    decision**: the embedder is local open-weight `bge-small` ([ADR-0007](0007-hybrid-retrieval-fulltext-first.md)),
    multimodal is agentic-to-text with **no** cloud embedding API
    ([ADR-0008](0008-multimodal-agentic-to-text-not-native-embeddings.md)),
    entailment (HHEM) runs locally, and the stores (Neo4j, Postgres+pgvector)
    are self-hosted containers. The classic embedding-egress leak cannot happen.
  - Observability already exports OTLP to any backend
    ([ADR-0010](0010-observability-opentelemetry.md)), point it at an on-prem
    Jaeger/Grafana, no code change.
  - The dataset abstraction ([ADR-0006](0006-dataset-agnostic-pipeline.md))
    isolates ingestion: only the adapter touches the source, so an air-gap
    deployment swaps in a local-corpus adapter instead of HF streaming.
- **Cons:**
  - Open-weight agentic quality is the real risk, multi-hop tool-use + citation
    discipline + ICD-203 calibration are harder for smaller local models than for
    Claude. This is a **validation** item, not an architecture one (the rubric +
    needle + reconciliation evals are exactly how to measure the gap per model).
  - Supply chain shifts onto the operator: open-weight repos are an attack
    surface (HF Safetensors conversion-hijack demonstrated; OWASP LLM03), so the
    model bundle needs signed import + chain-of-custody via a data diode.

### B. Two codebases / two harnesses (cloud + air-gapped)

- **Pros:** each tuned to its environment.
- **Cons:** doubles maintenance, drifts the analytic logic, and forks exactly the
  parts (gates, provenance, eval) that must stay identical for governance. Rejected.

### C. Cloud-only, defer air-gap

- **Pros:** simplest now.
- **Cons:** violates the brief's hybrid constraint and the target deployment
  reality; leaving it undocumented lets cloud assumptions harden into the code.

## Decision

**Adopt A, single codebase, single seam.** The fork is one env boundary plus
pre-staged infrastructure. Per-component swap points:

| Component | Cloud | Air-gapped substitution | Ariadne code change |
| --------- | ----- | ----------------------- | ------------------- |
| Orchestrator model | Claude API | open-weight on vLLM/TGI behind a **LiteLLM** proxy via `ANTHROPIC_BASE_URL` | **None** (env only) |
| Agent harness | Claude Agent SDK | same SDK, redirected | None |
| Graph store | Neo4j container | same, in-enclave | None |
| Relational + vector | Postgres + pgvector | same, in-enclave | None |
| Embedder | local `bge-small` (`embed` extra) | same | None |
| Entailment | local HHEM (`eval` extra) | same | None |
| LLM-rubric judge | Claude (`rubric` extra) | open-weight via the same proxy, or skip (advisory score) | None (env) |
| Dataset ingestion | HF `datasets` streaming | pre-staged local corpus via a local-file `DatasetAdapter` | adapter only |
| Observability | OTLP → any backend | OTLP → on-prem Jaeger/Grafana | None |

The analytic spine, gather→act→verify→synthesize loop, provenance ledger,
citation/tradecraft/governance gates, needle/reconciliation/rubric eval, is
**identical** across both. Only the model endpoint, the corpus source, and the
observability sink differ, none of which touch the analytic logic.

## Consequences

- The hybrid constraint is satisfied with **one codebase**; the air-gap "port"
  is an ops exercise (stage weights, run vLLM+LiteLLM, point env vars, mirror
  containers), not a rewrite.
- Prior local-first decisions (ADR-0007, ADR-0008) are validated: they pre-empted
  the embedding-egress leak that breaks most air-gapped RAG pipelines.
- The open question narrows from "how do we air-gap Ariadne?" to **"which
  open-weight model clears our eval bar?"**: answerable by running the existing
  rubric/needle/reconciliation harness against candidate local models.
- **Follow-ups** (tracked, not blocking): an explicit **no-egress CI guard**
  (fail the build on a new outbound dependency / a cloud-defaulting SDK), and a
  signed-model-bundle import process for the enclave.

## Sources

- [The Air-Gapped LLM Blueprint, egress-free deployments (2026-05)](https://tianpan.co/blog/2026-05-01-air-gapped-llm-blueprint-egress-free-deployment)
- [Claude Agent SDK with LiteLLM (LiteLLM docs)](https://docs.litellm.ai/docs/tutorials/claude_agent_sdk) · [Claude Code LLM gateway configuration](https://code.claude.com/docs/en/llm-gateway)
- [Running LLMs in air-gapped environments (2026-03)](https://dasroot.net/posts/2026/03/running-llms-air-gapped-environments/)
- [Connect to your own LLM using vLLM, air-gapped (Elastic docs)](https://www.elastic.co/docs/explore-analyze/ai-features/llm-guides/connect-to-vLLM)
- OWASP LLM Top 10, LLM03 supply-chain (open-weight repos as attack surface)
