# 0031, Net-effect ratification comparator — `ariadne compare`, measure don't read

- **Status:** Accepted (2026-06-07)
- **Deciders:** Ariadne maintainers
- **Refines:** [ADR-0020](0020-adaptive-self-improving-ariadne.md) (the ratify step of
  propose → ratify → freeze) · closes the loop opened by
  [ADR-0029](0029-distilling-analytic-skills-from-trajectories.md) (B2) +
  [ADR-0030](0030-reflexion-over-the-eval-harness.md) (B3) · builds on
  [ADR-0019](0019-retrieval-side-evaluation-for-sensemaking.md) (the eval as verifiable reward)

## Context

B2 distils a skill from a successful run; B3 proposes refinements from a failing one. Both
**propose**; a human **ratifies**. Today ratification is *reading* the proposed artifact — and
2026 skill-evaluation work is blunt that reading is not enough: **"you cannot reliably identify
bad skills just by reading the text,"** and **negative transfer happens in ~25% of cases**
(Microsoft SkillLens / SkillOpt). The defensible ratification step has to **measure** the
artifact's effect, not judge its prose. Ariadne already owns the measuring instrument — the eval
harness. The contestable questions: *what* to measure (a single delta? repairs and regressions?),
and *how to measure it soundly* given that agentic eval is stochastic. Hence this ADR.

## Decision drivers

- **Measure, don't read.** Negative transfer in a quarter of skills, undetectable by inspection,
  is the whole reason the ratify step needs a number. SkillGen marks a skill *active* only on a
  verifier's net gain — "explicit validation of skill effects, rather than assuming quality, is
  essential."
- **Net effect, not repair-rate.** Repair success alone is an incomplete picture: an artifact can
  fix more *and* break more. The comparator must surface **repairs and regressions separately**
  and net them, not report one improvement number.
- **Paired, same-instance comparison.** Agentic eval is stochastic; comparing a baseline and a
  candidate **on the same fixture/instance** induces matched realisations and reduces variance
  (tighter CIs, higher power). Comparing across *different* instances is meaningless — a hard error.
- **Disclose the harness.** A skill's effect is confounded if the model/profile/params differ
  between sides; comparisons must hold the harness constant (or flag that they don't).
- **Stochasticity needs trials.** A single before/after pair is noisy; multiple trials per side
  stabilise the signal. The comparator supports N-per-side and caveats small N.
- **The boundary holds.** The comparator only *reads* `eval.json` (the scorer's output); it never
  computes or alters a score — no evaluator tampering ([ADR-0020](0020-adaptive-self-improving-ariadne.md)).

## Considered options

1. **Ratify by reading the artifact (status quo).** *Rejected as sufficient.* Cannot detect the
   ~25% negative-transfer skills; "you cannot identify bad skills by reading the text."
2. **A single overall score delta (candidate − baseline).** *Rejected.* Hides the repair/regression
   structure (a net-zero delta can be one big repair masking one big regression), and a single run
   per side is dominated by stochastic noise.
3. **Re-run the eval inside the comparator (recompute scores).** *Rejected.* That makes the
   comparator a second scorer — drift from the canonical eval, and a step toward the loop touching
   its own grader. The comparator consumes the existing `eval.json`, full stop.
4. **`ariadne compare --baseline … --candidate …`: a deterministic net-effect comparator over
   eval'd runs — same-instance-gated, repairs/regressions separated, harness + small-N caveats.**
   *Chosen.* The hermetic core of the ratification check; *producing* the runs (a live workup with
   vs without the artifact, ~$0.5 each) is the separate, expensive wrapper this slice does not build.

## Decision

Adopt **option 4**, in `src/ariadne/learning/netcheck.py` + an `ariadne compare` command.

- **Same-instance gate.** Every baseline and candidate run must share the eval **fixture** (the
  instance); a mixed set raises `IncomparableRuns`. Paired same-instance comparison is what makes
  the delta a signal rather than instance noise.
- **Per-dimension net effect.** Over the gold-anchored dimensions (`grounded` as 1/0, `recall`,
  `trajectory`, `supporting_fact_f1`, `citation_coverage`), compute each side's mean and classify
  the move against the known ideal (1.0): **repair** (baseline below ideal → candidate at ideal),
  **regression** (baseline at ideal → candidate below), or directional **improvement / decline /
  neutral**. `net = repairs − regressions`.
- **Verdict.** *Reject* on any regression of a hard-gated dimension (`grounded` / `citation_coverage`)
  or `net < 0`; *ratify* on `net > 0` with no hard regression; *neutral* otherwise — the
  ratification evidence a human acts on (the agent never auto-applies).
- **Caveats, not silent assumptions.** The comparator emits caveats for a differing harness
  (model/profile/params across sides — the disclosure principle) and for small N (`< 3` per side —
  agentic eval is stochastic; paired trials recommended). It prints a readable verdict and, with
  `--out`, writes `comparison.json` for audit.

## Consequences

- The propose → ratify → freeze loop gains a **measured** ratify step: distil/reflect propose,
  `compare` quantifies the net effect, a human ratifies on evidence rather than on prose — the
  concrete answer to "is this learned artifact actually good?" and the guard against the ~25%
  that silently hurt.
- It composes B2 and B3 without new coupling: any two eval'd runs (with vs without a skill, before
  vs after a reflection's refinement) feed the same comparator.
- The eval stays the single scorer; the comparator is pure measurement over its output, so the
  loop still never touches its grader.
- Honest scoping (YAGNI): this slice is the **deterministic comparator**. Automatically *producing*
  the paired runs (orchestrating a live workup with/without the artifact), a real confidence
  interval / significance test over many trials, and wiring the verdict into an auto-ratify gate
  are deferred — named, not built. A single-run-per-side comparison is supported but caveated as
  noisy on purpose.

Sources: SkillGen verifier-gate on net gain ([arXiv 2605.10999](https://arxiv.org/html/2605.10999));
"you cannot identify bad skills by reading the text," negative transfer ~25% — Microsoft SkillLens /
SkillOpt ([SkillOpt, arXiv 2605.23904](https://huggingface.co/papers/2605.23904)); net-effect =
repairs − regressions, not repair-rate ([arXiv 2511.11012](https://arxiv.org/pdf/2511.11012));
stochastic agentic eval + paired same-instance variance reduction
([arXiv 2512.06710](https://arxiv.org/html/2512.06710v1),
[arXiv 2512.24145](https://arxiv.org/pdf/2512.24145)); disclose the harness when comparing
([arXiv 2605.23950](https://arxiv.org/html/2605.23950)).
