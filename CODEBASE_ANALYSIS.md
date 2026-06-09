# Ariadne — Codebase Analysis (merge-planning reference)

> **Purpose.** This document is a code-grounded architectural analysis of the `ariadne`
> repository, written as input for a planned merge of **three sibling repositories**. The
> downstream goal is to take the best features from each repo, so this analysis is biased
> toward *what is worth keeping*: every subsystem ends with an explicit "portable vs.
> domain-coupled" verdict, and the final section ranks merge candidates.
>
> **Method.** Claims are grounded in `path:line` against the working tree and cross-checked
> against current (2026) best practice via web search where a design choice is load-bearing.
> Generated 2026-06-09. Where the planning docs (ROADMAP/IMPL/ADRs) and the code disagree,
> the **code wins** and the discrepancy is flagged.

---

## 1. What Ariadne is

Ariadne is a **citation-grounded entity-sensemaking harness** built on the **Claude Agent
SDK**, shipped three ways from one codebase: a CLI (`ariadne`), an MCP server
(`ariadne-sensemaking` / `ariadne-mcp`), and a Claude Code plugin. It is the "Sensemaking
for Large Entities" effort of the **SCADS** program and is explicitly an *umbrella project*:
it defines integration seams so sibling pipelines (graph extraction, entity resolution,
multimodal indexing) surface as callable tools rather than being re-implemented.

The core loop: given a target **entity or organizational node**, an agent traverses
heterogeneous stores (graph + relational + full-text + semantic) through read-only MCP
tools, and produces a **cited analytic note** where every fact carries a `[cite:gN]`
provenance marker that resolves to the exact query that sourced it. Around that loop sits an
unusually complete rigor stack: a provenance-by-hook ledger, a multi-stage citation gate, an
ICD-203 analytic-tradecraft layer, a planted-needle evaluation harness producing *verifiable
rewards*, read-only + no-egress governance audits, an interactive offline HTML report, and a
bounded **propose → ratify → freeze** self-improvement loop.

**Maturity:** ~9.3k LOC of `src/`, 35 ADRs, published to PyPI, CI-green with branch
coverage. Self-described "Phase 1–5 substantially landed; Phase 6 (adaptive) first slices
shipped."

---

## 2. Technology stack & toolchain

| Concern | Choice | Evidence |
|---|---|---|
| Language | Python `>=3.12,<3.15` | `pyproject.toml:6` |
| Agent runtime | `claude-agent-sdk>=0.1` (official) | `pyproject.toml:33`, `cli.py:20-27` |
| Default model | `claude-opus-4-8` | `learning/__init__.py` `DEFAULT_MODEL` |
| MCP server | **FastMCP** from the official `mcp>=1.2` SDK | `mcp_server.py:22-30` |
| Graph store | Neo4j (`neo4j>=5.28`) via `mcp-neo4j-cypher@0.6` (read-only) | `graph/neo4j_server.py:16` |
| Relational store | Postgres via **crystaldba `postgres-mcp@0.3.0`**, restricted mode | `relational/postgres_server.py:24,55` |
| Vector/full-text | one Postgres: `tsvector`+GIN, `pgvector`+HNSW cosine, fused by RRF | `unstructured/document_store.py` |
| Embeddings | `bge-small-en-v1.5` (384-d, Apache-2.0) behind `embed` extra; `FakeEmbedder` default | `unstructured/embed.py:38,42-60` |
| Entailment | Vectara **HHEM-2.1-Open** behind `eval` extra | `provenance/entailment.py:31-48` |
| Datasets | HF `datasets>=3` (optional `data` extra) | `datasets/` |
| Observability | OpenTelemetry GenAI semconv (`api` core, SDK in `otel` extra) | `observability.py` |
| Build / packaging | `hatchling`, src-layout, PyPI `ariadne-sensemaking` | `pyproject.toml:125-130` |
| Tooling | `uv` + `ruff` + `ty` + `pytest` (+ `pytest-xdist`, `hypothesis`, `testcontainers`) | `pyproject.toml`, `Makefile` |
| Docs | Zensical (Material) → GitHub Pages | `zensical.toml`, `.github/workflows/docs.yml` |

**Optional-dependency extras** (deliberate hermetic core — none required to run the base
package): `data` (HF datasets) · `otel` (OTLP export) · `embed` (sentence-transformers) ·
`eval` (`transformers<5` + `torch` for HHEM) · `rubric` / `adaptive` (both `anthropic>=0.40`,
the only path that uses the **raw** Messages API). `pyproject.toml:54-89`.

> **Two distinct Claude surfaces** (decisive for billing/merge — see §11): the **main
> workup loop** runs through `claude_agent_sdk.query()` (subscription-capable); **four
> auxiliary call sites** (`mapping/llm_mapper.py`, `evaluation/judge.py`,
> `learning/distil.py`, `learning/reflect.py`) use raw `anthropic.Anthropic().messages.create()`
> with forced tool-use, behind the `rubric`/`adaptive` extras.

---

## 3. Architecture map

```
                          ┌──────────────────────────────────────────────┐
   ariadne CLI ──────────▶│  run_workup (cli.py)                         │
   ariadne-sensemaking ──▶│   build_options → ClaudeAgentOptions          │
   (MCP server / plugin)  │   async for msg in query(prompt, options):    │
                          │     AssistantMessage → note text + Skill obs   │
                          │     ResultMessage   → cost / usage / model     │
                          └───────────────┬──────────────────────────────┘
                                          │ MCP tool calls (read-only)
              ┌───────────────────────────┼───────────────────────────┐
              ▼                           ▼                           ▼
        mcp__neo4j__*              mcp__postgres__*            mcp__ariadne__*
   (mcp-neo4j-cypher, RO)   (postgres-mcp, restricted)   (in-process SDK tool:
        Neo4j graph             Postgres relational        hybrid_search RRF)
              │                           │                           │
              └─────────────► PostToolUse provenance hook ◄───────────┘
                              records gN, injects [cite:gN] back to the model
                                          │
                      ┌───────────────────┼───────────────────────┐
                      ▼                   ▼                         ▼
              Citation gate        Governance/assurance      Eval harness
        (recall/precision/         (read-only audit,         (planted needle:
         coverage + P-Cite          egress guard,            grounded/recall/
         repair loop)               weakest-link verdict)    trajectory + rubric)
                      │                   │                         │
                      └─────────► persisted run artifacts ◄─────────┘
                          note.md · provenance.jsonl · citations.json ·
                          governance.json · eval.json · rubric.json · report.html
                                          │
                          ┌───────────────┴────────────────┐
                          ▼                                 ▼
              Interactive HTML report          Self-improvement loop (propose→ratify→freeze)
              (offline, zero-dep)              distil / reflect / compare / ratify
                                               (gated by eval.json = verifiable reward)
```

**Data path (offline, separate from the live agent):** a heterogeneous source → a
`DatasetAdapter` → canonical records (`Entity`/`Relationship`/`Document`/`Attribute`) → the
indexer → live Neo4j + Postgres. `ariadne index --dataset <name>`.

### Module map (`src/ariadne/`, ~9.3k LOC)

| Package / module | LOC | Responsibility |
|---|---|---|
| `cli.py` | 1,414 | argparse CLI, the agent loop (`run_workup`, `build_options`), 12 subcommands |
| `report/html.py` | 1,234 | self-contained interactive HTML report (pure stdlib) |
| `learning/` | ~950 | Axis B self-improvement: `distil`, `reflect`, `ratify`, `netcheck` (compare), `runs` |
| `evaluation/` | 778 | planted-needle harness, reconciliation, utilization, ICD-203 rubric + judge |
| `mapping/` | ~700 | Axis A schema mapping: `llm_mapper`, `schema`, `ontology`, `propose`, `adapter` |
| `provenance/` | ~900 | ledger, PostToolUse hook, citation gate, governance, assurance, tradecraft, repair, entailment |
| `datasets/` | ~700 | canonical schema, `DatasetAdapter` registry, indexer, 4 adapters, HF streaming resilience |
| `unstructured/` | ~300 | Postgres full-text + pgvector hybrid search + injectable embedder |
| `graph/`, `relational/`, `introspect/` | ~400 | connector configs (read-only postures) + schema introspection |
| `mcp_server.py` | 221 | FastMCP server exposing `workup`/`list_datasets`/`connect_dataset`/`hybrid_search`/`list_profiles` |
| `runs.py`, `profiles.py`, `observability.py`, `egress.py`, `preflight.py` | ~700 | run identity/manifest, model profiles, OTel, no-egress guard, store reachability |

---

## 4. The agent orchestration loop (Claude Agent SDK)

`run_workup` / `build_options` (`cli.py:1038-1209`) is the spine. `ClaudeAgentOptions` is
assembled incrementally so unset envelope fields fall through to SDK defaults
(`cli.py:1065-1072`), then:

```python
return ClaudeAgentOptions(
    mcp_servers=mcp_servers,
    allowed_tools=allowed_tools,
    system_prompt=_SYSTEM_PROMPT,
    permission_mode="default",
    hooks={"PostToolUse": matchers},
    **extra,            # model, max_turns, max_thinking_tokens, skills/plugins
)
```

The consumption loop type-dispatches the async iterator (`cli.py:1195-1209`): `AssistantMessage`
→ accumulate `TextBlock.text` *and* OR-in any `Skill` invocations observed on the stream;
`ResultMessage` → harvest `result`, `is_error`, `total_cost_usd`, `usage`, `model_usage`. The
final note prefers the terminal `ResultMessage.result`, falling back to concatenated assistant
text.

Notable engineering details:
- **MCP server registration is incremental and gated** (`cli.py:1050-1064`): `neo4j` always
  on; `postgres` under `--sql`; the **in-process** `ariadne` SDK server (built by
  `create_sdk_mcp_server`, exposing only `mcp__ariadne__hybrid_search`) under `--semantic`.
  One shared provenance hook is bound per family via `HookMatcher(matcher="mcp__neo4j__.*", ...)`.
- **Skill wiring has two mutually-exclusive paths** (`cli.py:1073-1086`): the default sets
  `skills=["entity-workup"]`; the `ratify` path stages a per-arm plugin with
  `plugins=[{type:local,path}]`, `skills="all"`, `setting_sources=[]` so the staged plugin is
  the *sole* skill source. The docstring records the hard-won contract that `skills=[]` is an
  empty *allowlist* the SDK rejects every skill against — not "no skills" (ADR-0034 follow-up).
- **A tool-less repair caller** (`make_repair_caller`, `cli.py:1097-1126`) reruns `query()` with
  `mcp_servers={}` / `allowed_tools=[]` so the citation-repair pass can only rewrite text, never
  retrieve or mutate.
- **Skill invocations are read off the message stream, not a hook** (`provenance/skills.py`):
  Skill is prompt-expansion, so `PostToolUse` never fires for it (anthropics/claude-code#43630);
  the loop reads `ToolUseBlock(name="Skill")`, keyed on `input["skill"]` (the CLI tool-schema key,
  pinned from the bundled CLI's own schema).

**Trade-off — agentic search over a fixed pipeline.** The loop hands the model a *tool menu*
(graph / relational / hybrid) plus a routing skill, not a hardcoded retrieve→rerank chain.
Cross-modal corroboration and multi-hop discovery are emergent. This matches the **2026
"Adaptive RAG" consensus**: route by query — relationship/multi-hop → graph traversal, hard
ambiguous questions → an agent loop that decides what to retrieve and whether to retrieve
again ([Adaptive RAG 2026](https://jobsbyculture.com/blog/agentic-rag-guide-2026),
[RAG techniques 2026](https://blog.starmorph.com/blog/rag-techniques-compared-best-practices-guide)).
Ariadne's `entity-workup` SKILL.md encodes exactly this routing. The accepted cost is 3–10×
LLM calls per query, justified here because the target use case is high-value investigative
sensemaking.

> **Correction to the planning narrative:** there is **no prompt-caching handling in code** —
> a grep for `cache_read`/`cache_creation`/`cache_control` returns nothing in `src/`. The cache
> savings noted in IMPL.md are the SDK's reported `usage`, not Ariadne logic. Caching is left
> entirely to the SDK/transport.

---

## 5. Heterogeneous retrieval

### 5.1 Connectors — "official guardrailed server over hand-rolled"

Both database connectors *refuse to execute queries themselves*, delegating to a hardened MCP
server and allowlisting only read tools:
- **Neo4j** (`graph/neo4j_server.py`): `mcp-neo4j-cypher@0.6`, both `NEO4J_READ_ONLY=true`
  *and* `--read-only` (defence in depth), only `get_neo4j_schema` + `read_neo4j_cypher`
  allowlisted; the write tool is excluded entirely.
- **Postgres** (`relational/postgres_server.py:9-13,24,55`): crystaldba `postgres-mcp@0.3.0` in
  `--access-mode=restricted` (read-only transactions + execution caps + `pglast` parsing to
  reject COMMIT/ROLLBACK statement-stacking). The choice is grounded in a named CVE class — the
  official reference server had a read-only-bypass SQL-injection via statement-stacking (Datadog
  Security Labs). The server is pinned to Python 3.13 in an interpreter-isolated `uvx`
  subprocess (`pglast==7.2` lacks a 3.14 wheel).

### 5.2 Hybrid search — one Postgres, RRF-fused (a standout)

`unstructured/document_store.py` carries **three retrieval shapes in one database**:
`content_tsv tsvector GENERATED ALWAYS AS (...) STORED` + GIN (full-text via
`websearch_to_tsquery`/`ts_rank`); a `pgvector` column + **HNSW cosine** index
(`m=16, ef_construction=64`); and relational rows. `hybrid_search_sql` fuses the full-text and
vector legs in a *single SQL query* via **Reciprocal Rank Fusion**:
`COALESCE(1.0/(k+fts.rank),0) + COALESCE(1.0/(k+vec.rank),0)`, `k=60`, no score normalization.

Best-practice check: RRF with `k=60` is the **production-standard default** in 2026 —
scale-agnostic, no tuning, ~91% recall@10 as a baseline, and the pgvector+tsvector+RRF
combination is a documented pattern ([Hybrid search with RRF 2026](https://micelclaw.com/blog/hybrid-search-rrf/),
[pgvector + FTS + RRF](https://dev.to/lpossamai/building-hybrid-search-for-rag-combining-pgvector-and-full-text-search-with-reciprocal-rank-fusion-6nk)).
Ariadne's choice is squarely on the current consensus; the only "advanced" piece it omits is a
cross-encoder reranking stage (a reasonable scope choice — RRF alone is production-grade).

The **`Embedder` Protocol** (`unstructured/embed.py`) keeps this hermetic: `FakeEmbedder` is a
deterministic SHA-256 hash embedder for tests; `SentenceTransformerEmbedder` (default
`bge-small-en-v1.5`, lazy-imported, `normalize_embeddings=True`) is the real one behind the
`embed` extra. EmbeddingGemma-300m is noted as a gated swap.

### 5.3 Dataset abstraction — canonical schema + adapter registry (a standout)

The "make heterogeneous sources look uniform" seam:
- **Canonical schema** (`datasets/canonical.py`): four frozen dataclasses — `Entity`,
  `Relationship`, `Document`, `Attribute` — and `Canonical` as their union. Deliberately
  minimal: dataset specifics live in open `attributes`/`metadata` dicts, *never* new core
  fields. Each record routes to one store (Entity/Relationship→graph; Document→full-text+vector;
  Attribute→relational).
- **`DatasetAdapter` Protocol + `DATASETS` registry** (`datasets/base.py`): `name`,
  `entity_type`, `access: Literal["public","restricted"]`, `load()`, `eval_fixtures()`; adapters
  self-register at import.
- **Four shipped adapters** prove the seam spans modalities: `synthetic` (org graph),
  `enron` (real email corpus, header→graph + body→document, collapses repeat sender/recipient
  pairs into one `EMAILED` edge with counts), `lahman` (relational baseball CSVs → player/team
  entities + `PLAYED_FOR` year-edges), `worldspeech` (audio reasoned as text via transcript, no
  ASR). A fifth path, `MappingDrivenAdapter`, registers a ratified user `mapping.toml` as a
  dataset (see §9).
- **HF streaming resilience** (`datasets/streaming.py`): `bounded_stream` closes the underlying
  iterator in a `finally` (an abandoned streaming iterator leaves a prefetch thread alive that
  hangs teardown), and `stall_guarded` pumps a *factory* on a **daemon thread** so even the
  blocking `load_dataset` resolve is guarded and a wedged socket can't block interpreter exit
  (default 180s, `$ARIADNE_STREAM_STALL_S`). Small, pure, solves a real non-obvious bug.

### 5.4 The `entity-workup` skill

`.claude/skills/entity-workup/SKILL.md` encodes a **gather → act → verify → synthesize** loop:
learn each store's shape; route by question (graph for relationships/hierarchy/co-location,
relational for attributes, **prefer `mcp__ariadne__hybrid_search`** for free text with an
`execute_sql` + `websearch_to_tsquery` fallback); re-query decisive links and reconcile
cross-modal agreement/conflict; synthesize from a note template with an ACH on the decisive
finding, ICD-203 confidence, and a mandatory `[cite:gN]` on every fact and judgment.

---

## 6. Provenance & the citation gate (the rigor spine)

### 6.1 Provenance by hook

`provenance/hook.py` `make_provenance_hook(ledger)` is a closure returning a `PostToolUse`
callback. On every evidence-tool call (`EVIDENCE_TOOL_PREFIXES = ("mcp__neo4j__",
"mcp__postgres__", "mcp__ariadne__")`) it records the call into a `ProvenanceLedger`, assigns a
monotonic id `gN` (`g{len(entries)+1}`, source-agnostic "grounding"), and **injects
`additionalContext` back to the model** telling it to cite derived facts as `[cite:gN]`. The
ledger (`provenance/ledger.py`) stores `id/ts/tool/tool_input/response_excerpt` (truncated to
2000 chars) and sets `response_full_len` only when truncated — so the report can warn that the
evidence the analyst verifies against is partial. JSONL round-trip via `write_jsonl`/`read_jsonl`.

> **Correction:** subagent fan-out with per-worker `agent_id` attribution is **designed but
> deferred** (ADR-0015, gated by ADR-0005); no `agent_id` exists in `src/`. The single-closure
> shared-ledger design *is* subagent-ready by SDK semantics (one monotonic counter keeps `gN`
> globally unique with no merge step), but the `agent_id` column is a planned enrichment, not
> shipped.

### 6.2 The citation gate (`provenance/citations.py` + `entailment.py` + `repair.py`)

Three conditions, ALCE-grounded (Gao et al., EMNLP 2023):
- **Stage 1 — recall:** `find_uncited_claims` flags asserted sentences with no `[cite:gN]`.
  Sentence splitting uses **`pysbd`** (abbreviation-aware; a naive `[.!?]` regex orphaned `i.e.`/
  `U.S.`). `_iter_citable_claims` is the single classifier shared by the recall gate *and* the
  coverage metric, so they can't diverge.
- **Stage 2 — precision/entailment:** the injectable `EntailmentVerifier` Protocol with a
  **Vectara HHEM-2.1-Open** adapter (`entailment.py`, behind `eval` extra); flags a cited claim
  the concatenated evidence doesn't entail (premise=evidence, hypothesis=claim, threshold 0.5).
- **Coverage + P-Cite repair:** `citation_coverage` returns cited/total citable claims;
  `repair_citations_loop` (`repair.py`, `MAX_REPAIR_PASSES=2`) attaches ledger cites to uncited
  claims, measuring Δcoverage as the unrepaired-G-Cite baseline vs. repaired. Crucially **the
  deterministic gate terminates the loop, never the model's self-judgment** — sidestepping LLM
  self-refinement degradation. Only recall is repaired; dangling/unsupported are surfaced, not
  rewritten.

**Estimative/analytic routing (ICD-203/206).** `tradecraft.is_estimative` (WEP terms,
non-standard hedges, confidence statements) routes calibrated judgments *out of the entailment
gate* — an NLI model would wrongly reject an inference the evidence doesn't *literally* state —
while still requiring them to be cited. `is_analytic_judgment` (illative connectives:
therefore/thus/inferred…, deliberately excluding because/since/so) gives the ICD-206 exemption
where a judgment grounded earlier in its segment needn't repeat the cite. `is_analytic_caveat`
routes single-modality evidential limits out of the recall gate (ICD-206 single-modality
exemption).

---

## 7. Governance, assurance & no-egress guard

The unifying philosophy is stated near-verbatim in three files: **"verify the posture, don't
trust the config."**

- **Read-only audit** (`provenance/governance.py`): `audit_read_only` scans each ledger entry's
  statement text for any mutating verb across *both* query languages (Cypher
  CREATE/MERGE/SET/DELETE…, SQL INSERT/UPDATE/DROP/GRANT…), word-boundary-matched so
  `created_at` doesn't false-positive. It catches *attempts* (a write the connector blocked still
  appears in the ledger). `ariadne governance` re-audits a persisted run and gates: read-only
  breach → **exit 3** (security outranks all), citation failure → exit 1, clean → 0; `--strict`
  self-gates the live run.
- **No-egress guard** (`egress.py`): a context manager monkeypatching `socket.connect`/`connect_ex`
  with a loopback-plus-allowlist policy; `block=True` raises on the first non-allowlisted connect
  (CI gate), `block=False` records (audit). An **autouse fixture wraps the entire unit suite**
  (`tests/unit/conftest.py`), turning the air-gapped posture into a standing CI check — any test
  that reaches a non-loopback host fails the build — and a testcontainers integration test asserts
  the real load path connects only to the two enclave stores. Scope is stated honestly:
  connection-time TCP only; DNS/UDP out of scope.
- **Unified assurance verdict** (`provenance/assurance.py`): four axes (read-only=HARD/security,
  citations=HARD/quality, tradecraft=ADVISORY/quality, egress=POSTURE/data-integrity) fold into
  one `GovernanceVerdict`, **weakest-link, never averaged**: a HARD fail → FAIL; an ADVISORY
  finding → ADVISORY; POSTURE never moves status. Presented as a multi-axis "model card," not one
  composite number. This matches the 2026 standard that composite single-number assurance scores
  mislead and the weakest dimension must not be averaged away (the repo cites Kili 2026 and
  arXiv:2512.01166).

---

## 8. Evaluation harness — verifiable rewards (the most defensible feature)

`evaluation/` (778 LOC) implements **gold-free-by-construction verifiable rewards**: fixtures
plant a known needle in seed data; scoring is pure substring/marker matching over the note +
provenance ledger — no human annotation, no LLM in the deterministic path. This is the reward
the self-improvement loop gates on (§9), and it can run in CI with no API key.

- **Planted needle** (`evaluation/needle.py`): a fixture encodes `answer_markers` (in the note =
  *surfaced*), `traversal_markers` (in the ledger = *traversed*), `min_hops`, and optional gold
  edges. `grounded = recall==1.0 AND trajectory==1.0` — *"a note that names the bridge with no
  ledger query walking it is a guess and must fail."* For cross-store needles the traversal marker
  is the **relational table name**, so trajectory is only satisfied if the relational store was
  actually engaged (the graph cannot supply it).
- **Trajectory grades observations, not just actions** (`evaluation/_text.py`, ~73 LOC — the
  single most reusable file): `traversal_text` grades the *(action + data-retrieval observation)*
  pair, so an untyped `MATCH (n)-[r]- RETURN type(r)` query that *returns* `MEMBER_OF` gets
  credit. `is_schema_introspection` strips catalog/metadata observations (`CALL
  db.relationshipTypes`, postgres catalog tools) before scoring so schema *enumeration* can't
  false-positive traversal. Genuinely novel agentic-RAG eval insight (ADR-0024).
- **Supporting-fact F1** (HotpotQA/MuSiQue-style): grounded/gold = recall; grounded/surfaced =
  precision (penalizes named-but-not-walked edges). `statement_text` joins all string-valued tool
  args, so it is connector-agnostic.
- **Reconciliation as a first-class score** (`evaluation/reconcile.py`): a cross-store fact counts
  as reconciled only if the fact surfaced **and** reconciliation cue language is present **and**
  both stores were queried — separating analysis from recitation; corroboration and conflict
  scored separately.
- **Context-utilization** (`evaluation/utilization.py`): `|cited ∩ retrieved gN| / |retrieved gN|`,
  deliberately **descriptive and never gated** (exploratory / negative-confirmation retrieval
  legitimately lowers it); `None` (nothing retrieved) is distinct from `0.0` (all noise).
- **LLM-Rubric (ICD-203)** (`evaluation/rubric.py` + `judge.py`): scores the four standards the
  mechanical gates *cannot* see (alternatives / argumentation / relevance / accuracy), pointwise,
  criterion-separated (one dimension per API call), anchored 1–5 via forced `submit_score`
  tool-use. **Judge-bias mitigations**: explicit verbosity-neutrality, rationale-before-score,
  criterion separation. `--samples N` runs self-consistency: **median**-aggregate (outlier-robust)
  with the inter-sample **spread** reported as the judge's disagreement-with-itself (ADR-0035).
  Default `samples=1`.
- **Persistence + telemetry**: `eval.json` / `rubric.json` feed the report and emit the correct
  OTel **`gen_ai.evaluation.result` event** (name/score.value/score.label) plus an app-namespaced
  histogram (`observability.py`).

---

## 9. Adaptive & self-improving loop — propose → ratify → freeze (the most novel feature)

ADR-0020's epic: move from *code-extensible* to *runtime-adaptive* and *experience-improving*
**without** eroding the auditable spine. One rule makes it defensible — **the loop edits only
declarative, ratified artifacts; never its own gates, scorers, governance, or code.** This is
enforced *structurally*, and the enforcement is itself tested.

- **Axis A — adaptivity.** A1: read-only `introspect/postgres.py` (information_schema SELECTs) →
  a `BaselineMapper` (deterministic) or `ClaudeSchemaMapper` (forced tool-use inside a
  **bounded validator-terminated repair loop** `propose_with_repair`, `MAX_MAP_ATTEMPTS=3`, the
  *validator* not the model stops it) → `validate_mapping` → a ratified `mapping.toml` under
  `$ARIADNE_MAPPINGS` self-registers as a dataset (ADR-0025), DSN read lazily off env so it stays
  off argv. A2: a declarative `ontology.toml` (`domain→range`) injected as JSON-Schema `enum`s on
  the forced tool + `validate_against_ontology` (intrinsic-vs-relational routing). A3:
  `connect_dataset` activates a ratified store at runtime, hand-sending
  `notifications/tools/list_changed` (the official SDK doesn't auto-notify).
- **Axis B — self-improvement (bounded, audited).**
  - `distil` (B2): turns a workup into a named skill, gated by **`certify`** — distil *only* from
    a run the eval harness scored `grounded` (the external verifiable reward; "the agent can only
    learn from what an external gate already certified"). `distil --into` deepens an existing skill.
  - `reflect` (B3): failure-side, **gold-free by construction** — reads only the run's own
    artifacts, never the fixture gold, and a *source-inspection test* (`test_reflect.py:142-149`)
    asserts the module never imports the needle module. The LLM prompt forbids inventing the answer.
  - `compare` (`netcheck.py`): nets **repairs − regressions** on the *same eval fixture*; a
    regression on a gated dimension (`grounded`/`citation_coverage`) forces reject regardless of
    net. Only *reads* `eval.json`, never recomputes (the eval stays the single scorer).
  - `ratify`: stages candidate-OFF vs candidate-ON arms, runs N trials each, scores, feeds
    `compare`, then applies the **SkillTester invocation gate** — three honest states (observed /
    signal-present-but-not-fired → **abstain** / unrecorded → caveat). Freeze copies the candidate
    under `.claude/skills/` only on a clean ratify; default is propose-only (human keeps judgment).

Best-practice check: this is **textbook 2026 RLVR/self-improvement safety**. The design traces
to *Audited Skill-Graph Self-Improvement via Verifiable Rewards*
([arXiv:2512.23760](https://arxiv.org/pdf/2512.23760), which the repo already cites): verifier-backed
promotion gates, verifiable rewards over subjective preference, and the named operational risk
that deployed self-improvement loops create incentives for reward hacking and untraceable drift
([reward-hacking 2026](https://www.articsledge.com/post/reward-hacking)). Ariadne closes the
classic vectors *by construction*: evaluator-tampering (reads the score, can't recompute it),
train/test leakage (gold-free, test-enforced), misattributed capability (invocation gate
abstains), and in-context self-refine hacking (propose-only). That the boundary is a verifiable
property rather than a prompt instruction is the standout.

---

## 10. Interactive HTML report & supporting layers

- **`report/html.py`** (1,234 LOC, pure stdlib — `ast/html/json/re/pathlib`): a **self-contained,
  offline, zero-dependency** single `report.html` (tested: no `http`/`url(` references). Data is
  an embedded JSON island parsed once, breakout-guarded (`</`→`<\/`). It renders a verdict
  dashboard; the cited note with **clickable `[cite:gN]` → evidence drawer** that *unwraps the MCP
  tool-result envelope* (`_clean_evidence`), warns on truncation, and offers a copy-the-exact-query
  control for independent re-verification; a **force-directed entity subgraph** (real
  Fruchterman-Reingold layout) with a node drawer for pivoting; a reconciliation panel using the
  *same cue vocabulary as the eval*; and an analytic-evaluation panel with a gold-free "where this
  run fell short of ground truth" caveat block. A from-scratch Markdown→HTML pass even hoists
  phantom citation-only table columns into a caption.
- **Observability** (`observability.py`): OTel GenAI semconv, `invoke_agent`→`evaluate` span tree,
  correct `gen_ai.evaluation.result` *event* (not a metric instrument) + app histogram; no-op
  until an OTLP endpoint is configured.
- **Profiles + run identity** (`profiles.py`, `runs.py`): operator-curated model+envelope profiles
  (air-gap deployments omit cloud profiles so an analyst can't select one); immutable
  `runs/<dataset>/<slug>/<run-id>/` with a manifest tying artifact to OTel trace id, atomic
  `latest` symlink, and `merge_scores` so eval/rubric can fill scores later without crashing.

---

## 11. Distribution & CI/CD (strong, reusable)

- **Triple entry point** (`pyproject.toml:91-96`): `ariadne` (CLI), `ariadne-sensemaking` (MCP
  server, name == PyPI dist so `uvx ariadne-sensemaking` "just works"), `ariadne-mcp` (alias).
- **MCP-server-as-plugin triad**: FastMCP server + plugin `.mcp.json` (`{"command":"uvx",
  "args":["ariadne-sensemaking"]}`) + `marketplace.json`/`plugin.json` + a skill. A complete
  "library → Claude Code plugin" recipe with no bespoke glue. `connect_dataset`'s runtime
  `tools/list_changed` is a reusable dynamic-registration pattern.
- **CI = the local gate**: `ci.yml` calls `make lint` (so CI and local never drift), matrix
  py3.12–3.14, branch coverage, a governance job that runs `ariadne governance` on a fixture and
  expects exit 0.
- **Supply-chain posture**: every action **SHA-pinned**, enforced by `pin-check.yml`; `zizmor.yml`
  static workflow audit; patch-only Dependabot auto-merge; **trusted publishing (OIDC, no stored
  token)** for PyPI with `permissions: {}` + cache disabled (cache-poisoning hardening).

> **Merge-critical billing note (see the planned item in ROADMAP §5 / IMPL):** the **main
> workup loop is subscription-capable** (Claude Agent SDK), but the **four raw
> `anthropic.Anthropic()` sites** (rubric judge, schema mapper, distiller, reflector) are
> *always* API-key-billed. If a merge target wants "runs on the user's Claude subscription,"
> those four are the only hard API-key dependency and would need to stay a documented
> API-key-only tier (or be re-routed — but they depend on forced tool-use, which MCP sampling
> can't do).

---

## 12. Cross-cutting design patterns (the transferable DNA)

1. **Injectable-Protocol dependency injection everywhere.** `Embedder`, `EntailmentVerifier`,
   `AnalyticJudge`, `SchemaMapper`, `DatasetAdapter`, and the `call_llm` / `ArmRunner` / `ArmScorer`
   seams all have a hermetic fake + a real impl behind an optional extra. The entire system is
   testable with **no API spend and no live stores** (572+ unit tests, hermetic).
2. **Verify the posture, don't trust the config.** Read-only and no-egress are *re-checked against
   the actual tool trace / socket behaviour*, not assumed from connector config.
3. **Deterministic gate as verifiable reward.** A pure, gold-free, no-API scorer is the single
   source of truth that gates the LLM-driven self-improvement loop — and the LLM may never edit it.
4. **Official-guardrailed server over hand-rolled execution.** Both DB connectors delegate query
   execution to a hardened MCP server and allowlist only read tools.
5. **Dataset-agnostic canonical seam.** Four open dataclasses + an adapter registry absorb graph /
   email / relational / audio sources without touching the core.
6. **Research-provenance discipline.** Nearly every non-obvious decision carries a
   `# research(YYYY-MM):` note with an arXiv/source citation, and the design choices verified above
   (RRF k=60, agentic+graph routing, RLVR safety) all hold up against current best practice.

---

## 13. Notable trade-offs & honest limits (stated in-repo)

- **Agentic search costs 3–10× tokens** vs a fixed pipeline — accepted because the use case is
  high-value multi-hop investigation; would be "pure waste" for simple fact lookup.
- **Marker-based eval scores surface text, not semantics** — a note phrased unconventionally can
  miss `answer_markers`; mitigated by supporting-fact F1 and the LLM-rubric for semantic axes.
- **LLM-Rubric lacks a human-annotated calibration network** — the overall is the mean of
  dimensions (the rubric-scoring subset of the paper), stated as the honest limit.
- **Read-only audit is a regex over statement text** — cheap and deterministic, catches attempts,
  but scans `tool_input` not server execution.
- **Egress guard is connect-time TCP only** — honest that DNS/UDP are out of scope and it's a
  verification tool, not a sandbox.
- **Subagent fan-out is designed, not shipped** (ADR-0015); `agent_id` provenance is a planned
  column.
- **Known doc drift:** `zensical.toml`'s Decision-Log nav lists only ADR 0001–0020 while 0021–0035
  exist on disk (nav-only, not a code issue).
- **Environment-fragile carve-outs:** the `eval` extra pins `transformers<5` (5.x breaks HHEM); a
  torch-finalization segfault is worked around by `os._exit` in `__main__.py`; torch is pulled from
  a CPU wheel index on Linux/Windows. Any merge inheriting `eval`/`embed` inherits these.

---

## 14. Merge assessment — what to take from Ariadne

Ranked by portability × strength. "Portable" = near-zero domain coupling, lift-and-shift.

### Tier 1 — take wholesale (domain-agnostic, high-value)

| Feature | Files | Why |
|---|---|---|
| **Trajectory-grades-observations + anti-enumeration guard** | `evaluation/_text.py` (~73 LOC) | The sharpest, most novel idea in the repo, in pure dependency-free Python. Any multi-store agentic-retrieval eval can reuse verbatim. |
| **No-egress guard + autouse-fixture pattern** | `egress.py`, `tests/unit/conftest.py` | The single most lift-and-shift-able file: a "no unexpected egress" CI gate for any Python project, with honest scope. |
| **Provenance ledger** | `provenance/ledger.py` | Generic append-only tool-call ledger with `gN` ids, excerpt-truncation warning, JSONL round-trip. No domain coupling. |
| **Self-contained HTML report generator** | `report/html.py` | Pure-stdlib, offline, JSON-island, breakout-safe, with a reusable MCP-envelope unwrapper. Any JSONL-trace tool gets an offline viewer for free. |
| **Single-SQL hybrid RRF retrieval + injectable embedder** | `unstructured/document_store.py`, `embed.py` | One Postgres, no second datastore, no normalization, on the 2026 RRF consensus. Compact and self-contained. |
| **OTel `gen_ai.evaluation.result` emission** | `observability.py` | Correct current semconv (event, not metric). Drop-in for any evaluated GenAI system. |

### Tier 2 — take the pattern, adapt the vocabulary

| Feature | Files | Adaptation needed |
|---|---|---|
| **Weakest-link assurance verdict** | `provenance/assurance.py` | The `AssuranceAxis`/`GovernanceVerdict` folding is domain-neutral; only the four axis builders are app-specific. |
| **Citation gate (recall/coverage/repair)** | `provenance/citations.py`, `repair.py` | The ALCE-style recall + `[cite:gN]` convention + gate-terminated repair loop is reusable for any cited-generation system; the ICD-203/206 routing vocab is intel-specific. |
| **Verifiable-reward self-improvement loop** | `learning/` (`certify`/`compare`/`ratify`) | The gate *structure* (read-the-score-never-recompute, gold-free-by-test, invocation gate, propose-only) is the transferable asset; "grounded" must be redefined per domain. |
| **LLM-Rubric engine** | `evaluation/rubric.py`, `judge.py` | The injected-judge / forced-tool / median-self-consistency / bias-mitigation template is reusable; swap the four ICD-203 dimensions. |
| **Forced-tool + deterministic-validator + bounded-repair** | `mapping/llm_mapper.py` | A drop-in template for any structured-output-with-self-repair task, with a `call_llm` injection seam. |
| **Canonical schema + adapter registry + HF streaming resilience** | `datasets/` | Excellent normalization seam; the canonical dataclasses may need extending for other repos' modalities, but `streaming.py` is portable as-is. |

### Tier 3 — strong but tightly coupled (reference, don't lift)

- **ICD-203/206 tradecraft layer** (`provenance/tradecraft.py`): WEP bands, illative-connective and
  caveat lexicons — intelligence-analysis-specific. The *structure* (route estimative/analytic
  claims out of the entailment gate via injectable predicates) is portable; the vocabulary is not.
- **Connector configs** (`graph/`, `relational/`): the read-only postures and the
  guardrailed-server-over-hand-rolled principle transfer; the specific MCP servers and tool
  allowlists are wired to Ariadne's stores.
- **Planted-needle fixtures + synthetic seeds** (`infra/*/seed.*`, fixtures): dataset-specific by
  definition, but the `FIXTURES` registry idiom (a merge target supplies its own fixtures, the
  scoring engine is untouched) is the reusable extension point.

### Integration seams a merge can lean on

- The **`DatasetAdapter` Protocol** is the natural ingest seam for a sibling's output.
- The **MCP tool-family convention** (`mcp__<source>__*`) + the provenance hook's
  `EVIDENCE_TOOL_PREFIXES` is the natural runtime seam for a sibling exposed as a read-only tool.
- The **`eval.json` verifiable-reward contract** is the natural seam for any sibling that wants to
  gate learning on a deterministic score.
- `docs/integration.md` + `docs/patterns.md` already articulate these as first-class ports.

### Risks / conflicts to watch in a merge

1. **The raw-`anthropic` four-call dependency** vs. a subscription-billing goal (§11) — decide the
   billing model before merging the rubric/mapper/distiller/reflector paths.
2. **ML-extra fragility** (`transformers<5`, torch `os._exit`, CPU wheel index) — these constrain
   any merged environment that pulls `eval`/`embed`.
3. **Python `>=3.12,<3.15`** floor and the postgres-mcp Python-3.13 subprocess pin — version
   alignment across the three repos.
4. **The "never edit the scorer" boundary is load-bearing** — if a merge blurs the scorer/learner
   separation, the self-improvement safety argument collapses. Preserve the structural enforcement
   (and its source-inspection test).

---

## Appendix — quick reference

- **CLI subcommands (12):** `workup`, `eval`, `rubric`, `index`, `profiles`, `governance`,
  `report`, `map`, `distil`, `reflect`, `compare`, `ratify`.
- **MCP tools:** `workup`, `list_profiles`, `list_datasets`, `connect_dataset`, `hybrid_search`
  (+ runtime `workup_<name>`).
- **Run artifacts:** `note.md`, `provenance.jsonl`, `citations.json`, `governance.json`,
  `eval.json`, `rubric.json`, `subgraph.json`, `reflection.{md,json}`, `report.html`, `manifest.json`.
- **Exit codes:** 0 clean · 1 analytic/citation failure · 2 precondition · 3 read-only/security breach.
- **ADRs:** 35 (`docs/architecture/decisions/0001`–`0035`).

**External best-practice anchors used in this analysis:**
[RRF k=60 hybrid search 2026](https://micelclaw.com/blog/hybrid-search-rrf/) ·
[pgvector + FTS + RRF](https://dev.to/lpossamai/building-hybrid-search-for-rag-combining-pgvector-and-full-text-search-with-reciprocal-rank-fusion-6nk) ·
[Adaptive/Agentic RAG 2026](https://jobsbyculture.com/blog/agentic-rag-guide-2026) ·
[RAG techniques compared 2026](https://blog.starmorph.com/blog/rag-techniques-compared-best-practices-guide) ·
[Audited Skill-Graph Self-Improvement via Verifiable Rewards (arXiv:2512.23760)](https://arxiv.org/pdf/2512.23760) ·
[Reward hacking prevention 2026](https://www.articsledge.com/post/reward-hacking).
