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
  execution itself — `2N` real workups against real stores — was gated behind a key + stores and not
  run in this slice (deliberate spend), exactly as ADR-0031 deferred *producing* the runs; **it was
  subsequently run for real (2026-06-09 — see the live-execution follow-up below)**; (b) **recording**
  the invocation signal into the run manifest is the immediate follow-on (now shipped — see the
  follow-up below); (c) full counterfactual *trace* auditing and a real significance test over many
  trials.

> **Follow-up — recording the invocation signal, shipped 2026-06-08.** The original scoping above
> assumed a `PostToolUse` hook would fire for the built-in `Skill` tool. A June-2026 re-check found
> that is **false**: the Skill tool is handled as *prompt expansion* and never reaches the tool
> pipeline, so the hook never fires (anthropics/claude-code#43630, **closed not-planned** — the
> documented workaround is to parse the transcript). So recording reads the signal off the message
> stream instead: a skill call surfaces as a `ToolUseBlock(name="Skill", …)` in an
> `AssistantMessage`'s content, which `run_workup` already iterates — `provenance.skills`
> normalizes it to the bare frontmatter name (stripping any `plugin:` qualifier so a staged-arm
> skill matches its name) and `run_workup` persists the set to the manifest's `skills_invoked`, the
> key the gate reads. So a current workup always carries the signal (`None` now means only a legacy
> run). What remains gated behind the live execution (a) is *validating* that the block appears in
> the live stream; the `input` key it uses is **no longer** part of that — it is pinned to the
> primary source (2026-06-09): the Skill tool's input schema lives in the bundled CLI (the binary
> the SDK shells out to), and CLI v2.1.169's tool schema is `skill: z.string().describe("The name
> of a skill …")` + `args: z.string().optional()`, so the name is under `skill` (`args` carries
> arguments, not the name). The extractor reads the one confirmed key — the speculative
> `command`/`name`/`skill_name` fallbacks (tolerated "until a live run pins the key") were removed
> as now-known-dead speculative generality. `# research(2026-06): hooks do not fire for Skill
> (prompt-expansion bypasses the tool pipeline) — anthropics/claude-code#43630 closed not-planned;
> observe the streamed Skill ToolUseBlock; Skill input key = `skill`, read off the bundled CLI
> v2.1.169 tool schema (the SDK is a thin subprocess wrapper, schema is CLI-side).`

> **Follow-up — the staged-arm skills contract fix, shipped 2026-06-08.** Staging via `plugins=`
> loads the candidate skill to disk, but `build_options` also set `skills=[]` on the arm — and a
> June-2026 re-verification of the SDK contract (the standing rule: re-check the primary source,
> don't trust the prose) found that `skills=[]` is an empty *allowlist*, not "don't add project
> skills": the SDK's own `ClaudeAgentOptions.skills` docstring (v0.2.87) says *"to suppress every
> skill from the listing, use `[]`"*, and unlisted skills are *"rejected by the Skill tool"*. So the
> staged candidate could **never fire** — every `ratify` run would land in the
> *signal-present-but-never-invoked* state and **abstain on everything**, silently. The fix: the arm
> sets `skills="all"` (enable the staged skills; the SDK then auto-allows the bare `Skill` tool) and
> `setting_sources=[]` (the staged plugin is the *sole* skill source — no project/user skill leaks
> into the measured arm, the documented *"use the plugins option to load skills from a specific
> path"*), and the stager writes a minimal `.claude-plugin/plugin.json` so `--plugin-dir` recognizes
> the dir and the plugin name — hence its skills' `plugin:skill` namespace — is pinned, not derived
> implicitly. The option contract is pinned by hermetic tests; the CLI-level confirmation (the staged
> skill actually fires under these flags and is recorded `plugin:`-stripped, so `check_invocation`'s
> `expected` matches) is an executable integration assertion that runs free when the suite runs with
> stores + key — folding in the live-stream validation deferred above. `# research(2026-06):
> claude-agent-sdk skills= is an allowlist/context filter, [] rejects every skill (SDK
> ClaudeAgentOptions.skills docstring, v0.2.87); plugin skills are namespaced plugin:skill and a
> plugin manifest is optional but pins the name; restrict filesystem discovery with setting_sources=[]
> and load skills from a path via plugins= (code.claude.com/docs agent-sdk skills + plugins).`

> **Follow-up — the live execution, run 2026-06-09.** The deferred deliberate-spend tail (a, above)
> was run for real against live stores, closing it. Candidate: `closing-citation-audit` (the
> supplementary skill B3 `reflect` had proposed) vs the always-on `entity-workup` base; `-n 2`,
> graph-only Halberd. **4 real workups, $2.60, all exit 0.** Outcomes, all honest: (1) **the invocation
> gate works live** — the staged candidate fired in 1 of 2 candidate trials (model-driven invocation
> variance) and its `Skill` ToolUseBlock was recorded off the **live message stream**
> (`skills_invoked: ['closing-citation-audit', 'entity-workup']`), so `observed=True`. This is the live
> confirmation of both formerly-deferred validation items at once: *the streamed `Skill` block appears
> live* **and** *the `skill` input key* (pinned to the primary source the same day — the live stream's
> key was extracted correctly, the `plugin:` namespace stripped to the bare `name`). (2) **Verdict
> NEUTRAL** (repairs 0 / regressions 0): both arms saturate the fixture (all runs `grounded`,
> recall/trajectory/coverage = 1.0), so there is no delta — the SkillTester ~78% no-effect majority,
> *not* a failure, and `compare` correctly distinguished it from *abstain* (which is reserved for the
> skill **never** firing). A skill that only audits citations cannot improve an already-100%-cited
> baseline; the candidate arm did do *more* retrieval (15–17 graph calls vs 13) but it did not move the
> scored outcome. (3) **Propose-only held** — not applied (no clean net gain). (4) **Prompt caching
> live** (`cache_read_input_tokens` 250K–690K/run vs ~100 uncached). Small-N (<3/side) was caveated by
> `compare` as directional. The candidate skill and run artifacts are gitignored, so only this record
> persists. *Still deferred (c): full counterfactual trace auditing + a significance test over large N.*

Sources: Counterfactual Trace Auditing of LLM agent skills — with-skill vs without-skill paired
runs, effect visible under saturation/cancellation
([arXiv 2605.11946](https://arxiv.org/html/2605.11946)); SkillTester — matched baseline with the
skill disabled + an invocation gate against misattributing ambient capability, ~14% help / ~78%
no-effect / ~8% harm ([arXiv 2603.28815](https://arxiv.org/html/2603.28815)); and ADR-0031's
net-effect / same-instance / disclose-the-harness sources, inherited unchanged.
