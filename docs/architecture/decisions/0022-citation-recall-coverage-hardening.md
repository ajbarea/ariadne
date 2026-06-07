# 0022, Citation-recall coverage hardening — a P-Cite repair loop + abbreviation-robust segmentation

- **Status:** Accepted (2026-06-07)
- **Deciders:** Ariadne maintainers
- **Design:** [spec](../../superpowers/specs/2026-06-07-citation-coverage-hardening-design.md)

## Context

Live `workup` runs exit 1 on the citation gate despite producing high-quality notes.
The actual artifacts from two live runs (synthetic/Halberd, enron/vince.kaminski)
show two distinct causes:

- **Coverage gaps (6/7 flagged):** the agent's *synthesis / ACH* sentences (the
  decisive-finding restatement, the "Favoring H1…" verdict, trailing corroboration
  judgments) sit in their own paragraphs without the `[cite:gN]` of their basis,
  even though that evidence is cited in the bullets just above. The entity-workup
  skill has instructed against this since `547bc81` (2026-06-04) and the agent still
  slips — a prompt-only fix is empirically insufficient.
- **A gate false-positive (1/7):** a fully-cited enron sentence is mis-flagged
  because the naive sentence splitter breaks on the period inside **"i.e."** and
  orphans the tail past the last citation.

The pipeline is **pure Generation-Time Citation (G-Cite)**: the agent writes inline
`[cite:gN]` in one decoding pass, then the deterministic gate validates.

## Decision drivers

- **Coverage is the failure axis, not precision.** Both runs have `dangling: []`
  (perfect precision) and fail only recall. `# research(2026-06): G-Cite prioritizes
  precision at the cost of coverage; P-Cite-first is the high-stakes recommendation
  (arXiv:2509.21557).`
- **Don't punch a hole in the gate.** The flagged synthesis sentences genuinely
  lack a cite; the fix is to *carry the cites*, not to exempt synthesis from recall.
- **Bounded + deterministically terminated.** `# research(2026-06): LLM
  self-judgment refinement degrades over iterations (Self-Refine, arXiv:2303.17651);
  bound iterations and terminate on a deterministic check, not model self-judgment.`
  Ariadne already owns that deterministic check (`find_uncited_claims`).
- **Preserve the gate's hermetic, deterministic property** (no network, offline,
  reproducible) when fixing segmentation.
- **Reuse existing infrastructure** — the provenance ledger and the recall gate are
  the repair pass's inputs; no new evidence retrieval.
- **Conditional, legible cost** for a cost-conscious single maintainer.

## Considered options

### Closing the coverage gap

1. **Gate-driven P-Cite repair loop.** *Chosen.* After the G-Cite draft, the
   deterministic gate finds uncited claims; a bounded post-hoc pass attaches the
   `[cite:gN]` from the ledger (or softens an ungroundable claim); the gate re-checks
   and terminates. Adds P-Cite's coverage on top of G-Cite's precision — the
   documented high-stakes hybrid — using the gate we already have as the loop
   terminator, sidestepping self-refinement degradation. Cost is conditional (fires
   only on imperfect drafts) and bounded (≤2 passes).
2. **Stronger prompt only** (more forceful skill template, worked examples).
   *Rejected.* Already in place since 2026-06-04 and fails live; G-Cite's coverage
   ceiling is structural, not a wording problem.
3. **Exempt synthesis/ACH headlines from recall in the gate.** *Rejected.* Puts a
   hole in the rigor centerpiece; the synthesis claims *should* be grounded — the
   evidence exists in the ledger, the agent just failed to carry the cite.
4. **Constrained/structured decoding or a claim-assertion tool protocol.**
   *Rejected (YAGNI / over-build).* Large architectural change for a demonstrated
   failure a post-hoc pass resolves; G-Cite (generation-time) sacrifices coverage
   anyway per the research.

### Sentence segmentation

5. **PySBD (rule-based, abbreviation-aware).** *Chosen.* Zero runtime dependencies,
   offline, deterministic — preserves the gate's hermetic property; 97.92% Golden
   Rule Set (`# research(2026-06): arXiv:2010.09657`). Handles `i.e.`/`e.g.`/`U.S.`/
   decimals/titles as a class, not case-by-case.
6. **Curated regex abbreviation guard.** *Rejected.* Hermetic and dep-free, but a
   partial reimplementation of a solved problem that will keep leaking on
   un-enumerated abbreviations — the expedient patch the ROADMAP says to avoid.
7. **spaCy / wtpsplit (ML) segmenters.** *Rejected.* Accurate but pull heavy/model
   dependencies and break the hermetic default path; overkill for the gate.

## Decision

- Add a **bounded (≤2), deterministic-gate-driven P-Cite repair loop** to
  `run_workup`: `validate_citations` → if `uncited`, a **tool-less** repair pass
  (`provenance/repair.py`, injected `call_llm` for hermetic tests) attaches ledger
  `[cite:gN]` to flagged claims or softens the ungroundable ones → re-validate →
  stop on `ok` or after the cap. The persisted note/report/manifest are post-repair.
- Gate the loop behind **`--repair / --no-repair`** (default on); `--no-repair` is an
  eval lever for measuring raw-G-Cite vs. repaired coverage.
- Replace the naive sentence splitter in `citations._iter_claim_segments` with
  **PySBD**; all downstream recall/entailment logic is unchanged.

## Consequences

- Live workups reach clean exit 0 by *grounding* synthesis claims, not by weakening
  the gate; precision is untouched. The repair pass cannot introduce dangling cites
  (re-validated each pass) and never mutates the provenance ledger, so governance is
  unaffected.
- One small pure-Python dependency (`pysbd`) enters the gate; the hermetic, offline,
  deterministic property is preserved.
- **Costs:** a conditional extra LLM call when a draft has gaps (bounded, profile
  model); a graceful exit 1 remains possible if the model cannot ground a claim in
  ≤2 passes (correct behavior — the gate still has teeth). `pysbd` is rule-frozen
  (last release 2021) — acceptable and arguably desirable for a deterministic gate.

## Sources

- Generation-Time vs. Post-hoc Citation (P-Cite-first for high-stakes) — https://arxiv.org/abs/2509.21557
- Multi-Stage Self-Verification (citation refinement) — https://arxiv.org/pdf/2509.05741
- Self-Refine (iteration degradation → bound + deterministic terminator) — https://arxiv.org/abs/2303.17651
- PySBD: Pragmatic Sentence Boundary Disambiguation — https://arxiv.org/abs/2010.09657
- ALCE citation precision/recall (existing gate basis) — https://arxiv.org/abs/2305.14627
