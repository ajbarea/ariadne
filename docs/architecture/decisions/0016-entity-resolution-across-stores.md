# 0016, Entity resolution across stores — tiered, ingestion-first, auditable

- **Status:** Accepted (2026-06-05) — strategy decided; Tier 1 shipped, Tiers 2–3 gated on real unstructured ingestion
- **Deciders:** Ariadne maintainers

## Context

The brief names **reconciling one entity across modalities** as a core challenge,
and the foundation research left **cross-store entity resolution open**
([roadmap open question 2](../../roadmap.md)). Today the harness links a
canonical `Entity` ([ADR-0006](0006-dataset-agnostic-pipeline.md)) across the
graph, relational, and document stores by an **exact shared key**: the graph's
`Person.alias` equals the relational `personnel.alias`, and a document's
`source_entity_ids` is pre-populated by the dataset adapter. That works because
the synthetic seed *knows* the linkage.

It does not answer the real problem: deciding that records refer to the **same
real-world entity** when keys do not align — name variants ("Bob" vs "Robert"),
no shared key, conflicting attributes, and above all **free-text document
evidence** (Enron/Avocado email bodies and headers), where the link to a
canonical entity is not given and must be inferred. This ADR fixes the strategy
before that data lands, so the resolution layer is decided rather than improvised
under a deadline.

Note the scope boundary: **entity resolution** answers *"are these the same
entity?"*; **reconciliation** (already scored, `reconcile.py`) answers *"given
they are the same, do their attributes agree — and if not, is the conflict
flagged?"*. ER feeds reconciliation; conflating them hides where errors enter.

## Decision drivers

- **Auditability is the spine.** Every cited fact resolves to a ledger entry; a
  *link* between records is itself a claim an analyst must be able to question.
  No silent merges.
- **Precision over recall at the deterministic tier.** A wrong merge fabricates
  a connection — worse than a missed one in an analytic product.
- **Calibrated uncertainty (ICD-203).** A probabilistic link must carry its
  confidence, not be laundered into a fact.
- **Lean + staged.** Synthetic data pre-links; build heavier tiers only when real
  unstructured ingestion needs them (YAGNI, as with [ADR-0015](0015-subagent-fan-out-design.md)).

## What the 2026 evidence says

- **Cascade/hybrid is the consensus:** deterministic rules for high-confidence
  fields, LLM reasoning only for the ambiguous/unstructured residual — not
  LLM-for-everything.
- **Blocking is critical even with LLMs:** cheaply partition into candidate sets
  before any expensive comparison; LLM + blocking beats LLM-alone on *both*
  runtime and F1.
- **Shift entity linking to ingestion** (a pre-processing step), not a
  post-retrieval afterthought — it yields a reproducible, interpretable chain.
- **Auditable reasoning traces:** production ER attaches retrieved evidence +
  confidence to each linkage decision so analysts can reproduce it.

## Decision

Adopt a **tiered, ingestion-first** resolution cascade. Each tier only handles
what the cheaper tier above could not; every link is logged with its basis.

1. **Tier 1 — deterministic key match (shipped).** Exact canonical-id / `alias`
   match across stores. Highest precision, fully auditable, zero model cost. The
   primary path; keep it.
2. **Tier 2 — deterministic blocking + normalized match (gated).** Generate
   candidates cheaply (block on normalized name, alias set, email local-part),
   then compare by rule (case-fold, alias-set membership, exact attribute keys).
   Still deterministic and auditable; blocking is the scalability enabler the
   2026 work stresses.
3. **Tier 3 — LLM-adjudicated linkage for the residual (gated).** For candidates
   that survive blocking but lack a deterministic match (name variants,
   free-text mentions), the agent adjudicates *"same entity?"* — and the link is
   recorded as an **explicit, `gN`-cited, ICD-203-calibrated claim** in the
   provenance ledger (its basis quoted), never a silent merge. The note can then
   cite *why* two records were linked and at what confidence.

**Ingestion-first:** resolution runs at index time (`datasets/indexer.py`),
stamping each record with its canonical `Entity.id`, so retrieval reasons over
already-linked entities. Query-time resolution is the fallback for residual
cross-store ambiguity surfaced during a workup.

**Conflicts stay separate:** once Tiers 1–3 establish identity, attribute
disagreements are handled by the existing reconciliation path — flag, don't
silently pick (the Talon-location pattern).

**Gating (what is/isn't built now):** Tier 1 is in place and the synthetic
slice scores `grounded=True` with reconciliation working. Tiers 2–3 are
implemented when **real unstructured ingestion** (Enron/Avocado free text, Phase
B/C) makes deterministic keys insufficient — not before.

## Consequences

- The identity layer is now a named, tiered contract instead of an implicit
  exact-key assumption; "how do you link across stores?" has a dated answer.
- Auditability is preserved by construction: deterministic links by logged rule,
  LLM links by a cited, confidence-bearing reasoning trace. No silent merges.
- ER and reconciliation are explicitly separated, so eval can target each
  (residual: an ER-accuracy fixture analogous to the planted-needle harness).
- A full **multi-agent ER framework** (specialized matching/clustering agents) is
  noted and *not* adopted — overkill at this scale; if fan-out lands
  ([ADR-0015](0015-subagent-fan-out-design.md)) a resolution worker could host
  Tier 3, but that is not a near-term need.
- **Owed at implementation:** an ER-accuracy eval fixture and a smoke that a
  Tier-3 link is recorded as a citable `gN` with its confidence, before trusting
  it in a note.

## Sources

- [Efficient record linkage in the age of LLMs — blocking stays critical (MDPI, 2025/26)](https://www.mdpi.com/1999-4893/18/11/723)
- [Multi-Agent RAG framework for entity resolution — specialized agents, rule-based preprocessing + LLM reasoning, auditable reasoning traces (MDPI Computers 14/12)](https://www.mdpi.com/2073-431X/14/12/525)
- [Deterministic entity resolution in RAG pipelines — entity linking as an ingestion-time step, not post-retrieval](https://www.technetexperts.com/deterministic-entity-resolution-rag/)
- [(Almost) all of entity resolution — deterministic vs probabilistic foundations](https://pmc.ncbi.nlm.nih.gov/articles/PMC11636688/)
