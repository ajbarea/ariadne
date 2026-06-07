# 0032, Deepening a skill from new experience — `distil --into`, bounded and compare-gated

- **Status:** Accepted (2026-06-07)
- **Deciders:** Ariadne maintainers
- **Refines:** [ADR-0029](0029-distilling-analytic-skills-from-trajectories.md) (which deferred
  "deepening an existing skill") · the held-out gate is [ADR-0031](0031-net-effect-ratification-comparator.md)
  (`ariadne compare`) · a [ADR-0030](0030-reflexion-over-the-eval-harness.md) reflection can
  motivate a deepen

## Context

B2's `distil` *creates* a skill from one good run. But a skill should **improve from experience**,
not be authored once and frozen: "when an agent repeatedly exhibits a failure pattern, engineers
update the corresponding skill so one observed failure becomes a clarified procedure or an added
constraint." Trace2Skill's second mode is exactly this — *deepening* an existing skill, not only
creating new ones — and ADR-0029 deferred it. The contestable questions: how to integrate a new
run's lessons *without* the documented failure mode (overfitting to one trajectory's specifics →
fragmented, bloated skills), and how to know the deepened skill is actually better. Hence this ADR.

## Decision drivers

- **Procedural memory compounds.** A create-only `distil` can't absorb a second run's lessons; the
  value of a skill library is that skills get *better* across uses (the procedural-memory thesis).
- **Bounded, conflict-aware integration — not a rewrite.** Naive deepening "sequentially overfits
  to non-generalizable trajectory-local lessons"; the fix is bounded edits with conflict detection
  and format validation (Trace2Skill / SkillOpt's bounded add/delete/replace), integrating the
  *generalizable* lesson, preserving the existing skill's accumulated knowledge.
- **Trace-conditioned revision.** The operation is *existing skill + a new trace → a revised
  skill* (SkillRevise), a different operation from creating from scratch.
- **The held-out gate is `compare`.** SkillOpt accepts an edit only if it improves validation;
  Ariadne already owns that gate — [ADR-0031](0031-net-effect-ratification-comparator.md)'s
  net-effect `compare`. Deepen **proposes**; `compare` measures the revised skill against the
  original; a human **ratifies**. The propose → ratify → freeze spine and the same certified-source
  gate as B2 both hold.
- **LLM-only, honestly.** Integrating procedural prose needs the model. A deterministic deepen
  could only *append* the new run's moves — the bloat-and-fragmentation Trace2Skill warns against —
  so there is no deterministic deepen (the honest capability line, the inverse of create-mode where
  the deterministic path records faithfully).

## Considered options

1. **Re-distill from scratch, ignoring the existing skill.** *Rejected.* Discards the existing
   skill's accumulated (and possibly human-authored) knowledge; it is creation, not deepening.
2. **Deterministically append the new run's observed moves to the skill.** *Rejected.* Bloat and
   fragmentation — the exact failure mode — with no conflict resolution or generalization.
3. **Auto-overwrite the existing skill in place when a new good run arrives.** *Rejected.* An
   unratified edit enters the *active* skill (breaches the spine), and you cannot tell it helped
   without measuring — the very thing [ADR-0031](0031-net-effect-ratification-comparator.md) exists for.
4. **`distil --into <skill>`: an LLM bounded, conflict-aware revision of the existing skill from a
   new certified run, proposed for ratification and validated by `compare`.** *Chosen.*

## Decision

Adopt **option 4**, extending `distil` in `learning/distil.py` with a deepen mode.

- **Trace-conditioned revision.** `distil <run> --into <skill-dir>` reads the existing
  `SKILL.md` (frontmatter + body) and the new run, and the model proposes a **revised** skill that
  integrates the run's *generalizable* lesson — the prompt instructs a bounded integration that
  preserves the existing structure and does **not** hard-code this run's entities (guarding the
  overfitting failure mode). Reuses the `propose_skill` forced tool (name / description / body).
- **Certified-source gate.** Deepen integrates lessons only from a run the eval harness certified
  `grounded` — the same gate as create-mode (B2). You deepen from successes, not hallucinations.
- **LLM-only.** `--into` requires `--llm`; without it, a clear error ("deepening requires `--llm`;
  the deterministic distiller can only create, not integrate").
- **Propose, never overwrite.** The revised skill is written to `skills-proposed/<name>/` (it never
  overwrites the original); `distilled_by` is stamped `llm:<model>:deepen` and `source` records the
  deepening run. Ratification is **measured**: run `ariadne compare` (original vs revised on the
  same fixture) and ratify only on a net gain — SkillOpt's held-out edit gate, with a human in the loop.

## Consequences

- Skills now **compound from experience**: a second (third, …) good run can be folded into an
  existing skill rather than spawning a redundant new one — procedural memory, not a flat cache.
- Deepen + `compare` is SkillOpt's controlled edit loop made explicit and **human-ratified**: a
  bounded revision, accepted only on measured net gain. And B3 → deepen → compare is the full
  *failure-pattern → clarified-procedure → validated* path the consumer story describes.
- The eval gate is untouched and the active skill is never silently edited; only a ratified,
  measured revision freezes.
- Honest scoping (YAGNI): this slice deepens from **one** run into one skill. Multi-run batch
  consolidation (Trace2Skill's parallel fleet), a rejected-edit buffer for negative feedback
  (SkillOpt), union of the existing skill's structured prerequisites, and auto-applying a
  compare-ratified revision are deferred — named, not built.

Sources: Trace2Skill — deepening existing skills, the overfitting failure mode, conflict detection
([arXiv 2603.25158](https://arxiv.org/abs/2603.25158)); SkillOpt — bounded edits + a held-out gate
that accepts only validation-improving edits ([arXiv 2605.23904](https://arxiv.org/pdf/2605.23904));
SkillRevise — trace-conditioned skill revision ([arXiv 2606.01139](https://arxiv.org/html/2606.01139));
skills as version-controlled files updated when a failure pattern recurs (Externalization in LLM
Agents, [arXiv 2604.08224](https://arxiv.org/pdf/2604.08224)).
