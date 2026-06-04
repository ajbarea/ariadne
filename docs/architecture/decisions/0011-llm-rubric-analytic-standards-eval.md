# 0011, LLM-rubric scoring of analytic standards (ICD-203)

- **Status:** Accepted (2026-06-04)
- **Deciders:** Ariadne maintainers
- **Relates to:** [ADR-0010](0010-observability-opentelemetry.md) (rubric scores are a governance signal the observability layer can surface); the citation gate, the WEP tradecraft lint, and the planted-needle eval (the mechanical rigor checks this complements)

## Context

The brief's central challenge is **specification & validation**: "how do you
know what works?" Ariadne already answers part of it *mechanically*: the citation
gate scores sourcing (recall + entailment), the tradecraft lint scores expression
of uncertainty (ICD-203 WEP bands), and the planted-needle harness scores whether
the analysis traversed the ground-truth path rather than guessing. Those are
deterministic and hermetic.

But several ICD-203 analytic tradecraft standards are not mechanically checkable,
they require a *reader's judgment*: did the note weigh **alternatives**, **argue
logically** from its evidence, stay **relevant** to the analytic question, and
keep its **judgments proportionate** to the evidence? A regex cannot score these.
Without a measure of them, "does this analytic product meet tradecraft standards?"
stays a vibe check, and note quality cannot be tracked across runs.

## Decision drivers

- **Cover the standards the mechanical gates cannot**: complement, do not
  duplicate, the citation/WEP/needle checks.
- **Calibrated and debuggable, not a single opaque score**: a reviewer must see
  *why* a note scored low on a given standard.
- **Hermetic core**: the scoring engine must run in CI with no model and no
  network; only the real judge needs an API key, like the live-agent e2e.
- **Longitudinal**: usable as an overnight quality signal and an optional CI
  gate, so regressions in analytic quality surface.

## Considered options

### A. LLM-rubric, pointwise, criterion-separated (chosen)

A manually authored rubric, one dimension per uncovered ICD-203 standard, each
with anchored 1-5 descriptors, scored **pointwise** by an LLM judge, one
criterion at a time with structured (forced-tool) output, aggregated to an
overall mean. The deployable subset of LLM-Rubric (Hashemi & Eisner, ACL 2024).

- **Pros:**
  - Pointwise analytic rubrics are the documented best tool for "debugging and
    longitudinal monitoring" (vs pairwise, which suits model *selection*).
  - Criterion-by-criterion scoring is debuggable, each dimension's score +
    rationale shows exactly where a note fell short.
  - Anchored 1-5 levels are the per-level calibration the literature calls for;
    a narrow scale reduces score drift.
  - Injected-judge design keeps the engine pure: a fake judge makes the whole
    scoring/aggregation path hermetic; the real Claude judge sits behind the
    optional `rubric` extra.
  - Bias mitigations are explicit: the judge prompt scores quality *not length*
    (verbosity bias), and asks for rationale *before* score with a forced schema
    (format/anchoring bias).
- **Cons:**
  - LLM judges are imperfectly calibrated to humans; this is a directional
    quality signal, not ground truth.
  - The full LLM-Rubric method trains a small calibration network on human
    annotations to predict the overall human score. Ariadne has no annotated set
    yet, so we ship the rubric-scoring subset (mean of dimensions) and treat the
    calibration network as a documented extension for when annotations exist.

### B. Pairwise LLM-as-judge

- **Pros:** more reliable per-comparison; the standard for ranking candidates.
- **Cons:** needs both-orderings and quadratic calls; suits *model selection*,
  not scoring a single note against an absolute standard, which is the job here.
  Position bias is a first-order concern.

### C. Single holistic "rate this note 1-10" prompt

- **Pros:** cheapest; one call.
- **Cons:** an opaque vibe score with no per-standard breakdown, exactly the
  failure mode this ADR exists to avoid. Maximally exposed to length/format bias.

### D. No LLM eval, mechanical checks only

- **Pros:** fully deterministic, no API.
- **Cons:** leaves the judgment-requiring standards (alternatives, argumentation,
  relevance, accuracy) entirely unmeasured. Half the tradecraft picture.

## Decision

**Adopt A.** `evaluation/rubric.py` holds the pure engine, `ICD203_RUBRIC`
(four dimensions the mechanical gates do not cover, anchored 1-5), an
`AnalyticJudge` Protocol, and `score_note` / `score_note_dir`. `evaluation/judge.py`
holds `ClaudeAnalyticJudge`, behind the optional `rubric` extra (lazy `anthropic`
import), scoring one dimension per forced `submit_score` tool call. `ariadne
rubric <dir>` runs it (API-gated), informational by default, a pass/fail CI gate
with `--min`.

The four scored dimensions, chosen because the mechanical layer cannot see them:

| Dimension | ICD-203 standard | Why not mechanical |
| --------- | ---------------- | ------------------ |
| `alternatives` | #4 analysis of alternatives | Requires reading whether competing explanations were weighed |
| `argumentation` | #6 clear, logical argumentation | Requires judging whether reasoning follows from evidence |
| `relevance` | #5 customer relevance + implications | Requires judging the "so what" |
| `accuracy` | #8 accuracy of judgments | Requires judging whether claims overreach the evidence |

(Sourcing #2 → citation gate; uncertainty #3 → WEP lint; fact-vs-judgment →
`tradecraft.is_analytic_judgment`. Those stay mechanical.)

## Consequences

- The judgment-requiring ICD-203 standards become a **per-dimension, debuggable,
  trackable** score, closing the half of "how do you know it works?" the
  mechanical gates cannot reach.
- The score is a CI-gateable governance signal (`--min`) and a candidate
  observability metric (ADR-0010).
- The signal is **directional**: LLM-judge calibration is imperfect, and the
  human-calibration network is deferred until an annotated set exists. Treat
  rubric scores as relative/longitudinal, not absolute ground truth.
- This also motivates a future `entity-workup` skill-prompt improvement: telling
  the agent it will be scored on these four standards should raise note quality
  (the real notes currently weigh few alternatives and state few implications).

## Sources

- [LLM-Rubric: A Multidimensional, Calibrated Approach to Automated Evaluation (ACL 2024)](https://arxiv.org/abs/2501.00274) · [microsoft/LLM-Rubric](https://github.com/microsoft/LLM-Rubric)
- [ICD-203, Analytic Standards (ODNI)](https://fas.org/irp/dni/icd/icd-203.pdf)
- [Am I More Pointwise or Pairwise? Position Bias in Rubric-Based LLM-as-a-Judge (2026)](https://arxiv.org/abs/2602.02219)
- [Rubric-Based Evaluations & LLM-as-a-Judge, methodologies, biases, validation (2026)](https://medium.com/@adnanmasood/rubric-based-evals-llm-as-a-judge-methodologies-and-empirical-validation-in-domain-context-71936b989e80)
