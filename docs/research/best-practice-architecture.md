# Best-Practice Architecture for Agentic Entity Sensemaking

> **Provenance.** Synthesized 2026-06-01 from a deep-research pass: 6 angles,
> 29 sources fetched, 139 claims extracted, 25 adversarially verified (24
> confirmed, 1 refuted). Confidence labels and open questions are preserved so
> unsettled areas stay visible. Vendor-self-reported figures are flagged as such.

## Bottom line

As of mid-2026, the best-practice architecture is an **orchestrator-worker agent
loop on the Claude Agent SDK**. A lead agent runs the canonical *gather context →
take action → verify work → repeat* loop and dispatches **parallel,
context-isolated subagents**: each with a tailored system prompt and a
restricted tool set, to retrieve from heterogeneous stores (graph, relational,
vector/unstructured) via **MCP connectors**. **GraphRAG** is the core capability
for traversing organizational hierarchies and following implicit, multi-hop
relationships. Multimodal evidence is fused **agentically**: convert
imagery/video to structured text, then reason over it, rather than relying on a
single shared embedding space.

---

## 1. Harness design (Claude Agent SDK)

**The agent loop.** Anthropic frames agent design around the loop *gather context
→ take action → verify work → repeat*, and recommends **defaulting to agentic
search** (selectively loading context with bash-style `grep`/`find`/`tail` tools)
over semantic/vector RAG, adding semantic search only when faster retrieval is
needed. Semantic search is faster but less accurate, harder to maintain, and less
transparent. *(Confidence: high, 3-0. Caveat: the blog's phrasing is "we
suggest," softer than "prescribes.")*

**Orchestrator-worker pattern.** A lead agent (e.g. Opus) spawning parallel
subagents (e.g. Sonnet) **outperformed a single-agent baseline by 90.2%** on
Anthropic's internal research eval. Multi-agent systems excel precisely at tasks
involving heavy parallelization, information exceeding a single context window,
and many complex tools, the exact shape of multi-source entity sensemaking.
*(Confidence: high for the benchmark, 3-0; 2-1 for general suitability. Caveats:
vendor-internal eval (BrowseComp), not independently reproduced; the result is
specific to breadth-first queries and does **not** generalize to tasks needing
shared context or inter-agent dependencies; multi-agent burns ~15× more tokens;
token usage alone explains ~80% of performance variance.)*

**Subagents = parallelization + context isolation.** Each subagent runs in its
own fresh conversation; intermediate tool calls and results stay inside it and
only its final message returns to the parent. Each can have a tailored system
prompt and be limited to a specific tool subset, and multiple can run
concurrently. This directly enables one specialized retrieval agent per data
source without bloating the lead's context. *(Confidence: high, 3-0. Scope
qualifiers: API tiers throttle beyond ~5 concurrent subagents; subagents can't
communicate mid-execution; for dozens-to-hundreds of agents use a Workflow
instead.)*

**Memory for long investigations.** The lead agent saves its plan to external
**Memory** to persist context, because context beyond the model's window (the
cited system used ~200K tokens) is truncated; it then spawns fresh subagents with
clean contexts that maintain continuity through careful handoffs and retrieve
stored context rather than losing prior work. *(Confidence: high, 2-1. Caveat:
the 200K figure is model-specific, 1M-token Claude variants exist in 2026, but
the pattern holds.)*

→ For exact SDK mechanics, see the [Claude Agent SDK Reference](claude-agent-sdk-reference.md).

---

## 2. Multi-hop reasoning & GraphRAG

**GraphRAG is the core retrieval capability** for following organizational
hierarchies and implicit relationships. It leverages the structural/relational
information among entities to capture relational knowledge that flat chunk-RAG
cannot, and decomposes into a canonical three-stage architecture: **Graph-Based
Indexing → Graph-Guided Retrieval → Graph-Enhanced Generation**. The multi-hop,
context-preserving traversal is exactly what hierarchy-following requires.
*(Confidence: high for the capability/taxonomy, 3-0; 2-1 for the org-hierarchy
application.)*

**State of the art is agentic and iterative, not single-pass.** **GraphSearch**
organizes retrieval into six modules (Query Decomposition, Context Refinement,
Query Grounding, Logic Drafting, Evidence Verification, Query Expansion) enabling
multi-turn interaction, and uses a **dual-channel strategy**: semantic queries
over text chunks **and** relational queries over the graph, consistently beating
single-pass GraphRAG across six multi-hop benchmarks. *(Confidence: high, 3-0.
Caveat: self-reported, not independently replicated.)*

**Hybrid + agentic correction beats graph-only.** Pure graph-only retrieval
(GRAG) gives only marginal gains (+1.34 LLM-judge points) and shows an
all-or-nothing failure pattern; pairing graphs with **agentic correction
(AGRAG, +10.68)** or **hybrid graph+text (HRAG, +11.68)** yields large gains, with
the biggest benefit on multi-hop questions. *(Confidence: medium, 3-0 on the
figures / 2-1 on the "largest benefit" category. Caveats: CTI-domain-specific
preprint, not peer-reviewed; LLM-as-a-Judge is contested. A separate
hallucination-rate claim from the same paper was **refuted**: see below.)*

> **Contested.** Whether GraphRAG beats vanilla RAG is genuinely unsettled. It
> *loses* on simple fact lookup and time-sensitive queries (≈13% lower on Natural
> Questions, ~2.3× latency in one study) and is hurt by knowledge-graph
> incompleteness. "Graph-first" is justified **only** for multi-hop/relational
> queries; a **hybrid (graph + text + agentic correction)** design is the safer
> recommendation.

---

## 3. Heterogeneous connectors via MCP

Heterogeneous stores (relational, vector, graph) are best exposed to the agent as
**callable tools through the open MCP standard**. Google Cloud now offers managed
MCP servers spanning AlloyDB/PostgreSQL, Spanner, Cloud SQL, Bigtable, and
Firestore; **Spanner's MCP server lets an agent query graph, relational, and
semantic data together using both SQL and GQL** through a single multi-model
connector. Because the servers follow the open MCP standard, Claude connects by
adding a **Custom Connector** (a remote MCP URL) in settings, no complex config
files. *(Confidence: high, 3-0 on managed servers / multi-model; 2-1 on the
Custom-Connector detail. Caveats: vendor-promotional source, though corroborated
by Anthropic docs and press; a *protected* endpoint still requires OAuth client
credentials via UI.)*

The ecosystem also includes graph-native options (e.g. Neo4j publishing GraphRAG
retrievers as an MCP server, and Text2Cypher for natural-language → Cypher) as
practitioner patterns for the graph connector specifically.

**Design implication for Ariadne:** model each store as an MCP tool family
(`mcp__graph__*`, `mcp__relational__*`, `mcp__vector__*`); let the lead agent
route queries by source and reconcile overlapping results, with subagents owning
per-source retrieval.

---

## 4. Multimodal evidence fusion

Fuse multimodal evidence **agentically by converting images/video to structured
text**, not via a shared embedding space:

- **DeepMEL**: a multi-agent multimodal entity-linking framework with four
  role-specialized agents (Modal-Fuser, Candidate-Adapter, Entity-Clozer,
  Role-Orchestrator). Its **Modal-Fuser** uses an LLM's summarization plus a
  large visual model's visual-question-answering to extract **structured semantic
  text descriptions** of image entities, aligning visual evidence into the text
  modality before fusion.
- **V-Retriever**: reformulates multimodal retrieval as an **agentic reasoning
  process**: an MLLM selectively acquires visual evidence by calling external
  visual tools, interleaving hypothesis generation with targeted visual
  verification.

*(Confidence: high, 3-0. Caveats: V-Retriever is a non-peer-reviewed preprint
reporting its own ~23% gains; DeepMEL does use embeddings, but in a separate
candidate-generation step, not the fusion step.)*

**Design implication:** expose a **multimodal-to-text extraction tool** (VQA +
summarization) that turns imagery/video into structured, citable text the lead
agent reasons over alongside graph/SQL/text evidence.

---

## 5. Minimum-viable architecture

The smallest configuration that credibly demonstrates end-to-end value:

1. **Lead orchestrator** running the agent loop + external Memory for the plan.
2. **One graph connector** (Cypher/GQL), the multi-hop / hierarchy backbone.
3. **One relational connector** (SQL), structured facts/attributes.
4. **One vector/unstructured retriever**: free-text evidence.
5. **One multimodal-to-text extraction tool**: imagery/video → structured text.
6. **Provenance/citation tracking** so every surfaced fact traces to its source.

Source-specialized **subagents** own each connector and run in parallel; the lead
synthesizes their findings into the analytic product.

### Suggested phased build order

| Phase | Focus | Lands |
| ----- | ----- | ----- |
| **1** | Single-store vertical slice | graph connector + `entity-workup` skill + provenance hook + CLI (entity → cited note) |
| **2** | Heterogeneous retrieval | add SQL + vector connectors; source-routing + reconciliation; subagent fan-out |
| **3** | Multimodal fusion | multimodal-to-text extraction tool; cross-modal evidence fusion |
| **4** | Rigor, eval & integration | provenance surface, confidence handling, eval harness, SCADS sibling-tool interfaces |
| **5** | Deployment hardening | resolve the cloud-vs-air-gapped fork per component |

---

## 6. Deployment fork (cloud vs. air-gapped)

The deployment forks primarily at the **MCP connector layer** and the **model
layer**: managed cloud MCP + frontier Claude on one side; self-hosted MCP servers,
local graph/vector stores, and self-hosted or open-weight models on the other.

> **Low-confidence / open.** No claim in this pass was *adversarially verified*
> on the air-gapped fork specifically. Treat the above as directional. The
> [Claude Agent SDK Reference](claude-agent-sdk-reference.md#7-deployment) covers
> the concrete options (Managed Agents self-hosted sandboxes, SDK-behind-egress-
> proxy, open-weight proxy with feature-gap caveats) from first-party docs.

---

## Refuted & excluded

One claim was adversarially **refuted (1-2)** and is deliberately excluded: the
specific hallucination-rate percentages (RAG 45.8% / GRAG 34.1% / AGRAG 17.4% /
HRAG 12.4%) from the CTI paper. The *relative* benefit of hybrid/agentic-correction
designs survives; the absolute hallucination numbers do not.

## Open questions (unsupported by verified claims, treat as low-confidence)

1. **Air-gapped fork**: which open-weight models, self-hosted MCP servers, and
   local graph/vector stores substitute for frontier Claude + managed cloud MCP,
   and what capability is lost?
2. **Analytic rigor mechanisms**: best-practice provenance/citation tracking,
   grounding, confidence/uncertainty quantification, and applying **structured
   analytic techniques** (intelligence tradecraft) to agent outputs; how success
   is measured (traversal, cross-modal reconciliation, pivot-burden reduction,
   non-obvious connections).
3. **Entity resolution / record linkage**: reconciling one entity across graph,
   relational, and unstructured stores, and how the agent decides which store to
   query and resolves conflicts.
4. **Validated MVP & phased order**: the building blocks are established, but no
   empirically tested minimal end-to-end configuration was verified.

These are the highest-value targets for the next research pass.

## Key sources

- Anthropic, [Building agents with the Claude Agent SDK](https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk) · [Multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) · [Subagents docs](https://docs.claude.com/en/docs/agent-sdk/subagents)
- GraphRAG, [ACM TOIS survey 10.1145/3777378](https://dl.acm.org/doi/10.1145/3777378) · [arXiv:2501.13958](https://arxiv.org/abs/2501.13958) · [GraphSearch, arXiv:2509.22009](https://arxiv.org/abs/2509.22009) · [HRAG/AGRAG CTI eval, arXiv:2604.11419](https://arxiv.org/html/2604.11419)
- MCP connectors, [Google Cloud managed MCP servers](https://cloud.google.com/blog/products/databases/managed-mcp-servers-for-google-cloud-databases) · [Neo4j GraphRAG retrievers as MCP](https://neo4j.com/blog/developer/neo4j-graphrag-retrievers-as-mcp-server/)
- Multimodal, [DeepMEL (IP&M / arXiv:2508.15876)](https://www.sciencedirect.com/science/article/abs/pii/S0306457325004480) · [V-Retriever, arXiv:2602.06034](https://arxiv.org/pdf/2602.06034)
