# 0034, Automated net-effect ratification — `ariadne ratify`, produce the paired runs

- **Status:** Accepted (2026-06-08)
- **Deciders:** Ariadne maintainers
- **Refines:** [ADR-0031](0031-net-effect-ratification-comparator.md) (produces the paired runs
  `compare` measures — the wrapper ADR-0031 named-but-deferred) · [ADR-0020](0020-adaptive-self-improving-ariadne.md)
  (the ratify → freeze step of propose → ratify → freeze) · closes the loop over
  [ADR-0029](0029-distilling-analytic-skills-from-trajectories.md) (B2 distil) +
  [ADR-0030](0030-reflexion-over-the-eval-harness.md) (B3 reflect) +
  [ADR-0032](0032-deepening-a-skill-from-new-experience.md) (deepen)

## Context

`compare` ([ADR-0031](0031-net-effect-ratification-comparator.md)) gives ratification a *measured*
verdict — it nets a candidate artifact's **repairs** against its **regressions** on the same eval
instance. But it only *reads* `eval.json`; **a human must hand-produce the paired runs** — run a
workup with the candidate skill active, run it again without, N times each, on the same instance,
then point `compare` at the two sets. That manual dance is the open gap: `distil --into`'s own
output literally instructs *"run a workup with the revised skill vs the original, then `ariadne
compare`."* ADR-0031 named producing those runs as deferred. This ADR builds it.

2026 skill-evaluation work converged on the method. **Counterfactual Trace Auditing** runs the
*same model* with the skill and without it on the same task and records where the trajectories
diverge — it can see a skill's effect even when the final pass-rate is saturated or when helpful
and harmful effects cancel out. **SkillTester** formalizes the rig: a *matched baseline with the
skill disabled*, plus an **invocation gate** — verify the candidate skill actually fired in the
candidate arm, *"so ambient model capability is not misattributed to the skill itself."* Their
empirical finding is the whole reason this step has to be measured, not assumed: enabling a skill
improves the outcome in only **~14%** of paired trajectories, has no clear effect in **~78%**, and
*worsens* it in **~8%**.

## Decision drivers

- **Close the loop, end to end.** distil/reflect/deepen **propose**, `compare` **measures**, a
  human **ratifies** — but only if producing the evidence is one command, not a manual chore.
- **Counterfactual, paired, same-instance.** The candidate's effect is the *difference* a matched
  baseline (same instance, skill disabled) makes — inheriting ADR-0031's same-instance gate and
  N-per-side stochasticity caveats.
- **Invocation gate (the confound control).** If the candidate skill never fired in the candidate
  arm, any score delta is ambient model variance, not the skill — ratifying on it would be a
  measurement error. The verdict must abstain in that case.
- **The boundary holds ([ADR-0020](0020-adaptive-self-improving-ariadne.md)).** The eval stays the
  single scorer (each trial is scored once; `compare` only reads those scores). The loop freezes
  only ratified artifacts — never its gates or grader. Auto-freeze is gated on the eval's verdict,
  the external verifiable reward.
- **Propose by default, freeze on opt-in.** Consistent with the propose-only ethos of B2/B3, the
  default surfaces the measured verdict + the freeze command; `--apply` performs the freeze only on
  a clean *ratify*. The human keeps the judgment ([ADR-0020](0020-adaptive-self-improving-ariadne.md)).
- **Cost is real.** Each trial is a live workup (~$0.5 + live stores); `2N` of them is deliberate
  spend, not a quick check. The orchestration must be **hermetically testable without spending** —
  every retrieval/scoring seam injected — and the live execution gated behind a key + stores, like
  the existing live-profile validation and live judge.

## Considered options

1. **Leave ratification manual (status quo).** *Rejected.* The measured ratify step exists but is
   unreachable in practice — fiddly to stage a skill in/out per run and collect matched run dirs;
   the loop is closed on paper, not in use.
2. **Auto-produce *and* always auto-apply.** *Rejected.* Violates the human-keeps-judgment boundary
   and risks freezing a skill on a small-N or invocation-confounded verdict. Auto-freeze must be
   opt-in and gated on a clean ratify.
3. **`ariadne ratify <skill>`: stage the candidate OFF vs ON as two ephemeral skill plugins, run N
   trials of each over the same instance, score each, feed `compare`, gate on an invocation check,
   and `--apply` the freeze on a clean ratify.** *Chosen.* The counterfactual rig (CTA/SkillTester)
   wired onto Ariadne's existing seams: the SDK `plugins=[{type:local,path}]` loader toggles the
   skill per arm, the eval harness scores each trial, `compare` nets the effect.
4. **Full counterfactual *trace* auditing now (align trajectories, diff reads/writes/searches).**
   *Rejected for this slice (YAGNI).* The net-effect over eval scores is the ratification measure;
   trajectory-divergence auditing is a deeper diagnostic (closer to B3 `reflect`) and a future
   refinement — named, not built.

## Decision

Adopt **option 3**, in `src/ariadne/learning/ratify.py` + an `ariadne ratify` command.

- **Arm staging (the toggle).** For each arm, stage an ephemeral *plugin* directory and point the
  workup at it via the SDK's `plugins=[{"type": "local", "path": …}]` (the documented way to load
  skills from an arbitrary path — no working-tree mutation, no `cwd` games). The **baseline** arm
  carries the base skills as-is; the **candidate** arm carries them with the proposal layered in —
  *replacing* a same-named base skill (a deepened `entity-workup`) or *adding* a new one. The
  candidate's `name:` (from its `SKILL.md` frontmatter) is the **expected invocation**.
- **Paired trials.** Run `N` trials of each arm over the same `(dataset, entity, fixture)` via an
  **injected runner** (the live default wraps `run_workup`; tests inject a fake), scoring each run
  with the planted-needle fixture so every run dir carries an `eval.json`. Collect the two sets and
  hand them to `compare` — inheriting its same-instance gate, hard-gated-regression reject, and
  harness/small-N caveats unchanged.
- **Invocation gate (three honest states).** Across the candidate arm: **invoked** → proceed on
  `compare`'s verdict; **signal present but never invoked** → *abstain* (the delta is ambient
  variance, not the skill) with an explicit reason; **no signal recorded** → proceed on `compare`'s
  verdict but ride a caveat (the instrument is absent, not a confirmed miss — never a false reject).
- **Verdict → exit code.** `ratify` 0, `neutral`/`abstain` 0 (nothing is frozen), `reject` 1,
  `incomparable` 2 — mirroring `compare`.
- **Freeze on opt-in.** Default prints the verdict + the `mv` to ratify by hand. `--apply` performs
  the freeze (move the proposal under `.claude/skills/<name>`) **only** on a clean `ratify` with a
  confirmed (or unobserved-but-not-failed) invocation and no blocking caveat.

## Consequences

- The propose → ratify → freeze loop is **closed end to end, assisted**: one command produces the
  counterfactual evidence, measures it through the single scorer, and (opt-in) freezes a skill that
  earns it — the answer to *"does this learned artifact actually help, on this store?"* backed by a
  paired A/B, not by reading the prose.
- The invocation gate makes the SkillTester confound explicit: a verdict can no longer credit the
  base model's variance to a skill that never ran.
- The eval stays the single scorer; `ratify` never recomputes a score (it scores each trial once
  via the harness, then `compare` only reads). The boundary holds.
- **Honest scoping (YAGNI).** This slice ships the **orchestration + the invocation-gate logic +
  the arm toggle**, all hermetic and TDD'd against injected seams. *Deferred, named:* (a) the live
  execution itself — `2N` real workups against real stores — is gated behind a key + stores and not
  run here (deliberate spend), exactly as ADR-0031 deferred *producing* the runs; (b) **recording**
  the invocation signal into the run manifest is the immediate follow-on — the SDK contract is
  confirmed (the `PostToolUse` hook fires for the built-in `Skill` tool with its `tool_name`), and
  until a run records it the gate degrades to the unobserved caveat rather than a false reject;
  (c) full counterfactual *trace* auditing and a real significance test over many trials.

Sources: Counterfactual Trace Auditing of LLM agent skills — with-skill vs without-skill paired
runs, effect visible under saturation/cancellation
([arXiv 2605.11946](https://arxiv.org/html/2605.11946)); SkillTester — matched baseline with the
skill disabled + an invocation gate against misattributing ambient capability, ~14% help / ~78%
no-effect / ~8% harm ([arXiv 2603.28815](https://arxiv.org/html/2603.28815)); and ADR-0031's
net-effect / same-instance / disclose-the-harness sources, inherited unchanged.
