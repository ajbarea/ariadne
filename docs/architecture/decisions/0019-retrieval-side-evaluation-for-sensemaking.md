# 0019, Retrieval-side evaluation for a sensemaking workup — context utilization, not precision@k

- **Status:** Accepted (2026-06-05)
- **Deciders:** Ariadne maintainers

## Context

The analytic-rigor research pass (ROADMAP open-question #5) flagged **retrieval-side
context precision/recall** as a candidate eval delta: Ariadne scores answer-side
grounding (citation recall, HHEM entailment, supporting-fact F1, `grounded`,
reconciliation) but had no explicit *retriever*-quality signal — "of the evidence
the agent pulled, how much was signal vs. noise?" Before coding it, this ADR is a
June-2026 research pass on what "retrieval precision/recall" should *mean* for an
**agentic, iterative, multi-hop sensemaking** workup — which is a different animal
from single-shot RAG question-answering, where those metrics were defined.

## Decision drivers

- **Retrieval here is iterative agentic tool-calling, not a single ranked lookup.**
  A workup retrieves by a *sequence* of MCP calls across graph / relational / text,
  refining as it reasons (the 2026 industry baseline is ~2.8 retrieval rounds per
  query). There is no ranked chunk list, so there is no "rank *k*."
- **Exploration is legitimate tradecraft, not waste.** Analysis of competing
  hypotheses, checking alternatives, and *negative-confirmation* retrievals
  (establishing the absence of a tie) are good analysis — and they will not be
  cited. Penalising un-cited retrieval would punish exactly the breadth the
  sensemaking brief asks for. The exploratory-search / berrypicking / information-
  foraging literature (and NIST's entity-based sensemaking-tool evaluation) treats
  focused *and* exploratory retrieval as co-equal constituents of the process.
- **Prefer a deterministic signal (the eval-pyramid floor, [ADR-0011](0011-llm-rubric-analytic-standards-eval.md)).**
  Reach for an LLM judge only where a deterministic computation cannot answer the
  question.
- **Do not duplicate existing coverage.**

## Considered options

1. **Port RAGAS context-precision (precision@k).** *Rejected — structurally
   inapplicable.* Context-precision needs a ranked list of retrieved chunks plus a
   per-chunk relevance label, and rewards ranking relevant chunks first. Ariadne's
   retrieval is a sequence of agentic tool calls with no ranking. The 2026 SoK on
   Agentic RAG is explicit: precision@k / NDCG "assume single-pass retrieval with
   fixed result rankings," and agentic systems that iteratively refine queries
   "require fundamentally different measurement approaches" — recommending
   *trajectory-aware* axes instead (retrieval drift, context utilization,
   cumulative relevance).
2. **Port RAGAS context-recall (gold-attributable claims).** *Already covered.*
   Context-recall asks what fraction of the gold/reference claims are attributable
   to retrieved context — it needs a reference answer. Ariadne's planted-needle
   fixtures provide that gold, and `recall` (needle surfaced) + supporting-fact F1
   already measure whether the relevant evidence was retrieved *and traversed*
   (the SoK's "cumulative relevance"). Recall is only computable where gold exists
   (a fixture), not on an arbitrary live workup. No new metric is owed; name the
   existing scores as the recall-analog.
3. **Add a deterministic "context utilization" descriptive signal.** *Chosen for
   the precision-analog.* Of the distinct evidence the agent retrieved (`gN` in the
   provenance ledger), what fraction grounded a *cited* claim — computed from
   `provenance.jsonl` × `citations.json`, no model. This is the SoK's "context
   utilization" axis (do retrieved documents actually influence the reasoning).
4. **LLM-judge per-retrieval "passage utility" modeling.** *Deferred.* The 2026
   passage-utility approach scores each retrieval by relevance-to-query *and*
   contribution-to-final-answer — richer, but non-deterministic and costly per
   retrieval. Revisit only if the deterministic signal proves too coarse.
5. **Retrieval drift (successive-query alignment to the information need).**
   *Deferred candidate.* The SoK's third trajectory-aware axis; needs a
   query-vs-need similarity (embedding drift or a judge). Future work.

## Decision

Reframe "retrieval precision/recall" for the sensemaking domain rather than porting
the RAG-QA metrics verbatim:

- **Precision-analog → trajectory-scope CONTEXT UTILIZATION.** A deterministic,
  descriptive stat — `|distinct cited gN| / |distinct retrieved gN|` — surfaced in
  the eval output and as a report dashboard card with a plain-language definition.
  It is **informational, never a gate.** The definition states plainly that
  exploratory and negative-confirmation retrieval legitimately lower it: low
  utilization is a foraging-efficiency signal, not a failure.
- **Recall-analog → already shipped.** Gold-fixture needle `recall` + supporting-
  fact F1 are the cumulative-relevance / retrieval-recall measure; do not
  duplicate. Documentation should *name* them as such.
- **Do not port precision@k** — it assumes a ranked single-pass retrieval Ariadne
  does not perform.
- **Retrieval drift** and **LLM-judge passage-utility** are recorded as deferred
  future candidates, gated on the deterministic signal proving insufficient.

## Consequences

- The next code increment is small, deterministic, and honest: one context-
  utilization stat derived from artifacts already on disk, plus a dashboard card —
  no new gate, no false signal that punishes good breadth.
- The eval harness gains the SoK's "context utilization" axis without overclaiming
  RAGAS metrics that structurally do not fit agentic retrieval.
- The research changed the design: the original "port context precision/recall"
  candidate is correctly scoped down (precision@k dropped as inapplicable, recall
  recognised as already covered) — saving the revertable work of shipping a
  misleading retriever metric.

Sources: 2026 SoK on Agentic RAG — taxonomy, architectures, evaluation
([arXiv 2603.07379](https://arxiv.org/html/2603.07379v1)); RAGAS context-precision
([docs.ragas.io](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/))
and context-recall
([docs.ragas.io](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_recall/));
passage-utility modeling for agentic multi-hop retrieval
([PRISM, arXiv 2510.14278](https://arxiv.org/pdf/2510.14278)); exploratory-search /
sensemaking evaluation (NIST entity-based sensemaking-tool evaluation;
berrypicking / information-foraging).
