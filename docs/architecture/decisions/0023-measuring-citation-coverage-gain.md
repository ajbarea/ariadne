# 0023, Measuring the repair loop's coverage gain — claim-level structural citation coverage + Δ

- **Status:** Accepted (2026-06-07)
- **Deciders:** Ariadne maintainers
- **Builds on:** [ADR-0022](./0022-citation-recall-coverage-hardening.md) (the P-Cite repair loop)

## Context

[ADR-0022](./0022-citation-recall-coverage-hardening.md) shipped a bounded,
gate-terminated **P-Cite repair loop** that attaches ledger `[cite:gN]` to a
G-Cite draft's uncited synthesis/ACH claims, and it explicitly named the
`--no-repair` flag *"an eval lever for measuring raw-G-Cite vs. repaired
coverage."* That measurement was never built. The loop's value is currently
legible only as an **exit code** (Halberd exits 0 with repair, 1 without) — a
binary, not a number, and invisible across datasets.

Two facts make the measurement nearly free:

- `repair_citations_loop` already computes the **raw (pre-repair) report** at
  `repair.py:91` and then **discards it**, returning only the final report.
- The recall gate (`find_uncited_claims`) already defines the universe of
  *citable asserted claims*; the uncited set is its complement's failure side.

The brief's central challenge is **specification & validation** ("how do you
know what works?"). A shipped rigor capability whose effect we cannot quantify
is, by that standard, unverified.

## Decision drivers

- **Coverage is the axis the repair loop moves.** `# research(2026-06):` the
  G-Cite→P-Cite holistic evaluation defines **Coverage** as "the proportion of
  ground-truth citations present in the generated response" and reports that
  **P-Cite consistently achieves higher coverage** than G-Cite, plotting
  **Δcoverage = P-Cite − G-Cite** across datasets (arXiv:2509.21557, Fig. 3).
  Ariadne's draft is G-Cite and the repair pass is P-Cite — the *same* construct
  they ablate ("create a citation-free draft answer and then let P-Cite attach
  inline citations").
- **Δ relative to the unrepaired baseline is the established repair-gain
  convention.** `# research(2026-06):` Doctor-RAG reports "the absolute
  improvement, denoted as Δ, relative to the unrepaired baseline … the net
  increase in the aggregate score attributable to the repair process"
  (arXiv:2604.00865, §5.1).
- **Reuse the gate's claim universe** so the coverage denominator is *exactly*
  the set the recall gate already judges (DRY, no second definition of "claim").
- **Measurement, not a new gate.** The binary citation gate already has teeth;
  coverage is a *descriptive* number, like context-utilization (ADR-0019) — a
  `--no-repair` run may legitimately report low coverage.
- **Hermetic, deterministic, zero new dependency** — preserve the gate's
  offline/reproducible property.

## Considered options

### What to measure

1. **Claim-level structural citation coverage** — `covered / total` over the
   citable claim sentences the recall gate walks (covered = carries or is
   covered by an in-segment `[cite:gN]`; the complement of `uncited`). *Chosen.*
   It is the honest, deterministic, gate-consistent analogue of the papers'
   gold-Coverage when no per-claim gold exists, and it is `1.0` **iff** the
   recall gate passes — so the number and the gate never disagree.
2. **Gold-citation coverage** (the papers' exact metric: fraction of *ground-truth*
   citations present). *Rejected.* Ariadne has no per-claim gold citation set per
   workup (the planted needles carry gold *answers*, not gold per-claim cites);
   this would require hand-annotating every note.
3. **Raw uncited-count reduction** (`|uncited_before| − |uncited_after|`).
   *Rejected as the headline* — not normalized, not comparable across notes of
   different length — but **kept as a secondary legibility stat** (the
   `covered`/`total` counts are persisted alongside the fraction).

### How to measure the gain (ablation shape)

4. **Single-run before/after.** The raw draft *is* the unrepaired baseline;
   capture its coverage inside the repair run, before the first pass. *Chosen.*
   It is a true ablation on **one fixed draft** — it isolates the repair effect
   from draft-to-draft LLM variance — and costs nothing (the raw report is
   already computed). Matches Doctor-RAG's "relative to the unrepaired baseline."
5. **Independent A/B** (a `--repair` run vs a separate `--no-repair` run).
   *Kept as the corpus-level lever, not the primary.* Two independent drafts
   differ by sampling nondeterminism, conflating draft variance with the repair
   effect, and it doubles cost (~2× the ~$0.5 workup). Still meaningful
   **aggregated across a corpus** — the literal ADR-0022 lever — so retained:
   `--no-repair` runs report their (un)coverage as the G-Cite baseline.

### Granularity

6. **Segment-level** (a trailing cite covers its bullet/paragraph), as the
   current gate already scores. *Chosen* — one claim universe, one definition.
7. **Claim-level / positional fine-grained** (ALiiCE, the claim-level successor
   to ALCE). *Deferred — research-watch / known-limit.* A genuine refinement
   over segment-level, but it would fork the gate's claim universe; logged, not
   adopted.

## Decision

- Add `citation_coverage(note) -> CoverageStats(covered, total, fraction)` to
  `provenance/citations.py`, sharing the segment/exemption walk with
  `find_uncited_claims` (one classifier, two consumers). `fraction` is `None`
  when a note has no citable claims (undefined, not `0`).
- `repair_citations_loop` returns a `RepairOutcome(note, report,
  coverage_before, coverage_after, passes_run)`; `coverage_before` is the raw
  G-Cite draft, `coverage_after` the post-repair note.
- The workup persists `coverage` into `citations.json` as
  `{before, after, gain, covered, total}` — `gain = after − before` (the Δ),
  or `null` when repair did not run (`--no-repair`), which is semantically
  distinct from `0.0` (repair ran, nothing to fix).
- `EvalReport` gains a fixture-independent `citation_coverage` (the final note's
  coverage), so `ariadne eval` and the HTML report surface it **across datasets**
  — exactly like `context_utilization` (ADR-0019).
- The report renders a **coverage card** (before → after, Δ), consistent with
  the existing utilization card.

## Consequences

- The repair loop's value becomes a **measured Δcoverage** — per workup and,
  via the eval field, across datasets — instead of an exit code. This is the
  brief's "how do you know what works?" answered for this capability.
- Coverage is **never a gate**: the binary `ok`/`uncited` decision is unchanged;
  coverage is a descriptive measurement. No run that passed before now fails,
  and no run that failed now passes.
- **Honest scope:** *structural* (claim-attributed) coverage, not gold-citation
  coverage; entailment *precision* remains HHEM's job (ADR-0011 / the `--entail`
  gate); granularity is segment-level, not ALiiCE claim-level. All three are
  documented limits, not silent ones.
- Zero new dependency; the measurement is pure over `note × ledger`, hermetic
  and deterministic.

## Sources

- Generation-Time vs. Post-hoc Citation — Coverage metric + Δcoverage (P-Cite − G-Cite) — https://arxiv.org/abs/2509.21557
- Doctor-RAG: Failure-Aware Repair for Agentic RAG — Δ (absolute improvement vs unrepaired baseline) — https://arxiv.org/abs/2604.00865
- ALiiCE: Evaluating Positional Fine-grained (claim-level) Citation Generation — https://aclanthology.org/2025.naacl-long.23.pdf
- ALCE citation precision/recall (existing gate basis) — https://arxiv.org/abs/2305.14627
- Context-utilization precedent (descriptive, never-gated retrieval-side stat) — [ADR-0019](./0019-retrieval-side-evaluation-for-sensemaking.md)
