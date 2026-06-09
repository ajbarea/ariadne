# 0035, Self-consistency sampling for the analytic-rubric judge

- **Status:** Accepted (2026-06-09)
- **Deciders:** Ariadne maintainers
- **Touches:** `evaluation/rubric.py` (`score_note(samples=)`, `_aggregate`, `DimensionScore.spread`, `RubricReport.overall_spread`), `cli.py` (`rubric --samples`), `report/html.py` (disagreement badge)

## Context

The brief's central challenge is **specification & validation** — *"how do you know what
works?"* Ariadne answers it with a tiered eval pyramid; the top tier is the **LLM-Rubric**
([ADR-0011](0011-llm-rubric-analytic-standards-eval.md)): a Claude judge scores each ICD-203
analytic-quality dimension pointwise on an anchored 1-5 scale. That judge is a **single LLM
judgment per dimension**, and a single LLM judgment is the known-noisy part of any eval
pyramid — subject to position, verbosity, self-preference, and calibration-drift bias. The
[ROADMAP](../../../ROADMAP.md) named the fix as an open delta: *"DeepMind FACTS averages three
judges to cut single-judge bias; Ariadne uses one… the on-prem-safe variant is N sampled
judgments or N local judges."*

A June-2026 best-practice pass refined that naive framing materially (the reason the standing
"web-search before an arch decision" rule exists). Current consensus: the **cross-vendor
ensemble** (Claude + GPT + Gemini, majority vote) is the *launch-decision* default — but it
**tensions with Ariadne's air-gapped single-model branch** ([ADR-0012](0012-cloud-vs-air-gapped-deployment-fork.md))
and costs 3–5×; and *"a single judge with calibration is fine for weekly trends — reserve the
ensemble for launches and winrates inside the noise band near 50 %."* Ariadne's rubric is
exactly the monitoring case (pointwise, longitudinal), with one genuine decision point: the
`--min` CI gate. The on-prem-safe slice the research *does* endorse is **self-consistency
sampling plus reporting the judge's reliability**, used where a score actually decides something.

## Decision drivers

- **Air-gap-compatible** — no cross-vendor dependency (ADR-0012's single-model seam stands).
- **Default unchanged** — single judgment stays the default; it is defensible for monitoring,
  and a 3–5× cost must be opt-in.
- **Robust to an outlier judgment** — one anomalous draw must not move the reported score.
- **Surface reliability, don't hide it** — the analyst (and the `--min` gate) should see *where
  the judge is unstable*, not just a point score.
- **Free / hermetic to build** — the judge is an injected `AnalyticJudge`, so the aggregation is
  TDD'd with a fake; only an opt-in live `--samples` run spends.

## Considered options

1. **Cross-vendor ensemble (Claude/GPT/Gemini majority vote).** The 2026 launch-decision gold
   standard, ~30–40 % bias reduction. *Rejected:* breaks the air-gapped single-model branch
   (ADR-0012) and costs 3–5×; it is the wrong tool for a pointwise on-prem monitoring rubric.
2. **Same-model N-sample, mean aggregation.** *Rejected:* the mean is dragged by a single
   outlier judgment (a lone 1 among 5s), which is precisely the noise self-consistency exists to
   reject.
3. **Same-model N-sample, MEDIAN aggregation + report the inter-sample stdev (chosen).** Median
   is robust to an outlier draw; the stdev (`spread`) is a first-class **reliability signal** —
   `0.0` when the judge is unanimous/confident, larger where it wavers. Optional via `--samples N`
   (default `1` = today's single judgment). On-prem, no new dependency.
4. **Pin a controlled sampling temperature for `samples > 1`.** *Considered, not done.* Self-
   consistency only works if the judge samples with variance. A live probe confirmed it already
   does at the API default: 5 draws of the `accuracy` dimension on a real Halberd note returned
   **5, 4, 4, 4, 5** (median 4, spread ≈ 0.49), with distinct rationales. So no temperature change
   is needed for the feature to be live-effective; pinning an explicit sampling temperature (and
   injecting the judge's client to test it hermetically) is a named future refinement, not this
   slice.

## Decision

Adopt **option 3**. `score_note(note, judge, rubric, *, samples=1)` judges each dimension
`samples` times and **median-aggregates**, keeping a rationale *from a sample at the median* so
the prose explains the reported score. `DimensionScore.spread` and `RubricReport.overall_spread`
(both default `0.0`, backward-compatible) carry the population stdev of the draws — the judge's
disagreement with itself. `ariadne rubric --samples N` exposes it; the run report renders a `±σ`
disagreement badge per dimension and overall (shown only when `spread > 0`, so single-sample and
legacy `rubric.json` render unchanged). Odd `N` is recommended (no median tie); raise it for a
score near the `--min` gate, where one noisy judgment should not decide pass/fail.

## Consequences

- **The judge's reliability is now legible**, not assumed. A `4.75/5 (±0.40)` tells an analyst
  far more than `4.75/5`: it says *where* to trust the score. This is the honesty the eval
  pyramid's noisiest tier was missing.
- **Default behavior is unchanged** (zero regression): `samples=1` is a single judgment with
  `spread=0.0`, which current best practice confirms is fine for longitudinal monitoring.
- **Small `N` can read unanimous by chance** — a 3-sample run on the same note above happened to
  draw `4,4,4` and reported `±0.00`, while 5 samples revealed the `4↔5` waver. So `N≥5` is the
  honest choice for a borderline score; the `spread` is only as informative as `N`.
- **Live-validated** for ~$0.15: `ariadne rubric --samples 3` aggregated correctly end to end
  (CLI → median → `rubric.json` → report badge), and the determinism probe confirmed the judge
  samples with genuine variance, so the signal is real.
- *Deferred (named):* an explicit controlled sampling temperature (with judge-client injection to
  test it hermetically); a small-`N` caveat surfaced in the report.

## Sources

- LLM-judge bias taxonomy + mitigation, and *single-judge-with-calibration is fine for monitoring;
  reserve ensembles for the noise band* — [Future AGI, "LLM-Judge Bias Mitigation (2026)"](https://futureagi.com/blog/evaluating-llm-judge-bias-mitigation-2026/);
  [Label Your Data, "LLM as a Judge: A 2026 Guide"](https://labelyourdata.com/articles/llm-as-a-judge).
- Self-preference bias is real and measurable — [Quantifying and Mitigating Self-Preference Bias of LLM Judges (arXiv 2604.22891)](https://arxiv.org/html/2604.22891v2);
  [Judging the Judges (arXiv 2604.23178)](https://arxiv.org/html/2604.23178).
- Multi-judge averaging lineage — DeepMind **FACTS Grounding** (three-judge average); the on-prem
  variant is N sampled judgments, not N vendors (ADR-0012 constraint).
- Self-consistency by sampling-and-aggregating — Wang et al., *Self-Consistency Improves Chain of
  Thought Reasoning* (arXiv 2203.11171); median over mean for robustness to an outlier draw.
- `# research(2026-06): cross-vendor judge ensembles are the launch-decision default but air-gap-incompatible (ADR-0012) and 3-5x cost; single calibrated judge is fine for longitudinal monitoring, self-consistency sampling + reliability-reporting is the on-prem slice for decision points.`
