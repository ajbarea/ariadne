# Citation-recall coverage hardening — design

- **Date:** 2026-06-07
- **Status:** Accepted (autonomous session; research-grounded, no approval gate)
- **ADR:** [0022](../../architecture/decisions/0022-citation-recall-coverage-hardening.md)

## Problem

Live `workup` runs produce excellent analytic notes but **exit 1** on the citation
gate. Two real runs on this machine (synthetic/Halberd, enron/vince.kaminski) each
failed recall with uncited claims. Inspecting the actual `citations.json` +
`note.md` artifacts shows **two distinct failure modes**, not one:

1. **Genuine coverage gaps (6 of 7 flagged claims).** The agent's *synthesis /
   ACH* sentences — the decisive-finding restatement, the "Favoring H1…" verdict,
   trailing corroboration judgments — land in their own paragraphs or as flat
   trailing assertions **without** carrying the `[cite:gN]` of their basis. The
   evidence is cited in the supporting bullets just above; the synthesis sentence
   that rests on it is not. The skill already instructs against this (since
   `547bc81`, 2026-06-04) yet the agent still slips on secondary synthesis lines —
   a **prompt-only nudge is demonstrably insufficient**.

2. **A gate false-positive (1 of 7).** The enron fragment *"self-attributed
   forwards — and should not be read as 953 distinct inbound correspondents"* is
   **fully cited** (`[cite:g26]` earlier in the sentence). The recall gate's naive
   sentence splitter (`(?<=[.!?])\s+`) breaks on the period inside **"i.e."** and
   orphans the tail as a pseudo-sentence after the last citation. Analytic notes
   are abbreviation-rich (`U.S.`, `e.g.`, `cf.`, decimals, titles), so this class
   will recur.

## Research (2026-06)

- **Generation-Time vs. Post-hoc Citation** ([arXiv:2509.21557]): G-Cite (answer +
  citations in one pass) **prioritizes precision at the cost of coverage**; P-Cite
  (add/verify citations after drafting) achieves **high coverage** with competitive
  correctness and moderate latency. Recommendation: **P-Cite-first for high-stakes
  applications.** Ariadne is currently **pure G-Cite**, and our live runs show the
  exact predicted signature — perfect precision (`dangling: []` both runs), failing
  coverage. We are sitting on the documented weak spot of the approach we chose.
- **Multi-Stage Self-Verification** ([arXiv:2509.05741]): a refinement stage where,
  "for each key factual statement, the LLM inserts corresponding citation sources
  from verified evidence." This is P-Cite as a refinement pass — our exact shape.
- **Self-Refine** ([arXiv:2303.17651]) and the broader self-correction literature:
  **"specificity collapses over iterations as models increasingly fail to
  recognize correct answers"** — naive LLM self-judgment loops *degrade*. Mitigation:
  **bound the iterations and use a deterministic terminator, not LLM self-judgment.**
  Ariadne already has a deterministic terminator (`find_uncited_claims`), so the loop
  is gated by code, not by the model second-guessing itself.
- **PySBD** ([arXiv:2010.09657]): rule-based, abbreviation-aware sentence boundary
  disambiguation; **zero runtime dependencies**, offline, deterministic; 97.92% on
  the Golden Rule Set (+25% over the next-best pure-Python tool). Preserves the
  gate's hermetic property. Reinventing it with a curated regex is the "expedient
  patch" the ROADMAP says to avoid.

## Design

Two contained changes, shipped together because the live runs revealed both.

### A. Abbreviation-robust segmentation (fixes the false-positive class)

Swap the naive `_SENTENCE_SPLIT_RE.split(line)` inside
`citations._iter_claim_segments` for **`pysbd.Segmenter(language="en",
clean=False).segment(line)`** (one module-level segmenter, reused). Everything
downstream is unchanged: bullet/numbered-marker stripping still happens first, and
`last_cited` / `is_judgment` / caveat logic still operate per segment. This fixes
both recall (`find_uncited_claims`) and entailment (`find_unsupported_claims`),
which share the same iterator. `clean=False` preserves the `[cite:gN]` markers and
original spans verbatim.

### B. Gate-driven P-Cite repair loop (fixes the coverage gaps)

After the agent emits its G-Cite draft, run a **bounded, deterministic-gate-driven
post-hoc citation pass**:

```
note  = <agent draft>                       # G-Cite, precision-first (unchanged)
report = validate_citations(note, ledger)
for _ in range(MAX_REPAIR_PASSES):          # bounded (default 2)
    if report.ok or not report.uncited:     # deterministic terminator
        break
    note   = await repair_citations(note, ledger, report.uncited, call_llm=…)
    report = validate_citations(note, ledger)
```

- **New module `src/ariadne/provenance/repair.py`:**
  - `build_repair_prompt(note, ledger_entries, uncited) -> str` — pure, unit-testable.
    Gives the model the full draft (so it sees where each `gN` was already cited in
    the supporting bullets), the ledger as `gN → tool_input + response_excerpt`, and
    the flagged sentences, with one rule: for each flagged sentence, **append the
    `[cite:gN]`(s) from the ledger whose evidence supports it** (typically the cites
    already on the bullets it summarizes); if **no** ledger entry supports it, soften
    it to a calibrated ICD-203 judgment or drop it. Change nothing else; never invent
    a `gN` absent from the ledger.
  - `async def repair_citations(note, ledger, uncited, *, call_llm) -> str` — builds
    the prompt, calls the injected `call_llm`, returns the revised note. `call_llm`
    is injected so the core is **hermetically testable** with a fake (mirrors the
    existing `EntailmentVerifier` / predicate injection style).
- **`cli.py` wiring:**
  - `build_repair_options(model)` — a **tool-less** `ClaudeAgentOptions` (no MCP
    servers, no `entity-workup` skill, repair-specific system prompt) so the pass
    cannot retrieve more or wander; it only rewrites text.
  - Production `call_llm` wraps the SDK `query(...)` with those options at the run's
    profile `model`; assembles the returned `TextBlock`s.
  - `run_workup` gains a `repair: bool = True` param; the loop sits between
    `validate_citations` and `write_outputs`. The persisted `note.md`, `report`,
    metrics, and manifest reflect the **post-repair** note.
  - CLI flag `--repair / --no-repair` (default repair on). `--no-repair` is an
    **eval lever** — it measures raw G-Cite coverage vs. the repaired result, which
    is exactly the citation-recall metric the eval roadmap wants.

### Why a loop terminated by the deterministic gate (not pure prompt, not LLM self-judge)

- **Pure prompt** (status quo): tried since 2026-06-04, fails live. G-Cite's coverage
  ceiling is structural per the research.
- **LLM self-judgment loop:** degrades over iterations (Self-Refine finding).
- **Gate-driven P-Cite loop:** the deterministic `find_uncited_claims` decides when
  to stop, so there is no self-judgment degradation; the LLM only *attaches* cites it
  can ground in the ledger. Bounded passes cap latency/cost; the pass only fires when
  a draft actually has gaps (conditional cost). This is the high-stakes-appropriate
  P-Cite-first recommendation, adapted to the deterministic gate we already own.

## Components & boundaries

| Unit | Responsibility | Depends on |
|---|---|---|
| `citations._iter_claim_segments` | segment note into claim sentences (now pysbd) | `pysbd` |
| `repair.build_repair_prompt` | render the P-Cite repair instruction (pure) | — |
| `repair.repair_citations` | one post-hoc pass via injected `call_llm` | ledger, `call_llm` |
| `cli.run_workup` loop | bounded gate→repair→re-gate; persist repaired note | both above |
| `cli.build_repair_options` / `call_llm` | tool-less SDK call at profile model | claude-agent-sdk |

## Data flow

`agent draft (G-Cite)` → `validate_citations` → **if `uncited` & repair on** →
`build_repair_prompt` → `call_llm` → revised note → `validate_citations` → loop ≤2 →
final report → `write_outputs` + manifest + `workup_exit_code`.

The provenance ledger is **never mutated** by repair (no new tool calls); the pass
only attaches existing `gN` or softens prose, so governance (read-only audit) and
dangling-cite precision are unaffected, and `validate_citations` re-checks dangling
on every pass.

## Testing (TDD, hermetic)

1. **Segmentation (red→green):** new `test_citations` cases — a fully-cited sentence
   containing `i.e.` / `e.g.` / `U.S.` / a decimal is **not** flagged uncited
   (currently red under the regex; green after pysbd). Keep all existing recall/
   entailment tests green.
2. **`build_repair_prompt` (pure):** asserts the prompt contains the flagged
   sentences, the ledger `gN` + excerpts, and the "only existing `gN` / soften
   otherwise" rule.
3. **Repair loop (hermetic):** a fake `call_llm` that appends the correct `[cite:gN]`
   → `validate_citations` becomes `ok` within ≤2 passes; a fake that cannot fix →
   loop exits after `MAX_REPAIR_PASSES` with the claim still flagged (graceful exit 1,
   no infinite loop). `--no-repair` path leaves the draft untouched.
4. Whole-repo `make lint` + full unit/smoke suite green before any live run.

## Scope / YAGNI

- **In:** segmentation robustness; the P-Cite repair loop; the `--repair` eval lever.
- **Out (YAGNI):** constrained/structured decoding; a claim-assertion tool protocol;
  Proof-Carrying-Numbers tokens for numeric claims ([arXiv:2509.06902] — the general
  repair already covers numeric facts); repairing `dangling`/`unsupported` (different
  failure modes, empirically absent live — repair targets `uncited` only).
- **YAGNI exception justification:** the repair loop is *not* speculative — it is the
  research-backed fix for a **demonstrated, twice-reproduced** failure that the
  cheaper prompt-only fix already failed to resolve.

## Sources

- Generation-Time vs. Post-hoc Citation — https://arxiv.org/abs/2509.21557
- Multi-Stage Self-Verification (citation refinement) — https://arxiv.org/pdf/2509.05741
- Self-Refine: Iterative Refinement with Self-Feedback — https://arxiv.org/abs/2303.17651
- PySBD: Pragmatic Sentence Boundary Disambiguation — https://arxiv.org/abs/2010.09657
- Proof-Carrying Numbers (considered, rejected) — https://arxiv.org/pdf/2509.06902
- ALCE citation precision/recall (existing basis) — https://arxiv.org/abs/2305.14627
