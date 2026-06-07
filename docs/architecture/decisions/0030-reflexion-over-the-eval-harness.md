# 0030, Reflexion over the eval harness — `ariadne reflect`, grounded and gold-free

- **Status:** Accepted (2026-06-07)
- **Deciders:** Ariadne maintainers
- **Refines:** [ADR-0020](0020-adaptive-self-improving-ariadne.md) (axis B3, reflexion over the
  eval harness) · builds on [ADR-0019](0019-retrieval-side-evaluation-for-sensemaking.md) +
  [ADR-0023](0023-measuring-citation-coverage-gain.md) (the eval + citation gate as verifiable
  reward) and [ADR-0029](0029-distilling-analytic-skills-from-trajectories.md) (B2, the
  success-side counterpart)

## Context

B3 is the **failure-side** counterpart to B2. Where B2 distils a skill from a certified-good
run, B3 reflects on an **under-performing** run and proposes a refinement. The raw material
exists per run — `eval.json` (scored dimensions), `provenance.jsonl` (the trajectory),
`note.md`, `citations.json`, `governance.json`. The contestable questions: (1) what makes
reflexion *reliable* rather than the model re-judging itself with the same blind spots; (2) how
to ground the reflection **without** either of the two reward-hacking vectors — editing the
scorer, or reading the held-out gold; (3) an autonomous self-refine loop vs propose-only. Hence
this ADR.

## Decision drivers

- **The verifiability constraint.** Intrinsic self-correction is not a quality gate: the model
  that erred evaluates the error with the same blind spot, and performance does not reliably
  improve (often degrades). It becomes reliable only against an **external truth signal** —
  which Ariadne already owns: the eval harness ([ADR-0019](0019-retrieval-side-evaluation-for-sensemaking.md))
  and the deterministic citation gate ([ADR-0023](0023-measuring-citation-coverage-gain.md)).
- **The reward-hacking taxonomy.** 2026 work that *measures* agent evaluation-integrity names
  exactly two compromise vectors: **evaluator tampering** (editing the code that computes the
  metric) and **train/test leakage** (accessing held-out labels/test data). A defensible B3
  must make *both* structurally impossible, not merely discouraged.
- **In-context reward hacking (ICRH).** A closed, deploy-time self-refine loop (reflect → apply
  → re-score → repeat) drifts and games its own feedback — and scaling the model worsens it. A
  human in the loop breaks it.
- **Reflection grounding.** Self-correction must rest on cited, executable evidence (the CRITIC
  pattern), not the model's say-so — a clean fit for Ariadne's citation ethos.
- **Architectural consistency.** Reuse B2/A1's spine: propose → ratify → freeze, a deterministic
  core + an `--llm` enrichment, over the same `RunArtifacts` seam.

## Considered options

1. **An autonomous self-refine loop (reflect → auto-apply → re-score → repeat).** *Rejected.*
   ICRH / spontaneous reward hacking in iterative self-refinement; and an unratified artifact
   re-enters the loop — a breach of [ADR-0020](0020-adaptive-self-improving-ariadne.md)'s spine.
2. **Let the reflection read the fixture gold to explain *why* a dimension failed.** *Rejected.*
   That is the **train/test-leakage** vector the integrity benchmarks measure: the agent would
   learn the held-out answer, scoring better without getting better.
3. **Intrinsic self-critique (the model judges its own note, no external score).** *Rejected by
   the verifiability constraint* — same blind spots, not a gate.
4. **`ariadne reflect <run>`: an eval-triggered, gold-free, evidence-cited reflection that
   *proposes* refinements for human ratification; deterministic diagnosis + `--llm` reflexion.**
   *Chosen.*

## Decision

Adopt **option 4**, in `src/ariadne/learning/reflect.py` + an `ariadne reflect` command.

- **Trigger / gate.** `reflect` requires `eval.json` — the external verifiable reward must
  exist; no eval ⇒ refuse (the verifiability constraint, mirroring B2's certification gate). A
  run whose every gold-anchored dimension already sits at its ideal yields **no findings**
  ("clean — nothing to refine"); the reflection does not invent defects.
- **Gold-free by construction (closes train/test leakage).** `reflect` reads only the run's own
  artifacts — the eval **scores**, the trajectory, the note, `citations.json`, `governance.json`
  — and **never the fixture gold** (it does not import `needle.FIXTURES`). Two evidence classes:
  - **own-evidence findings** — `citation_coverage < 1` / `grounded = false` cite the agent's
    *own* uncited / dangling / unsupported claims; a **redundant-queries** finding cites
    exact-duplicate ledger entries. The evidence is the agent's behaviour, not the answer key.
  - **score-triggered findings** — `recall` / `trajectory` / `supporting_fact_f1` below ideal
    are flagged by the external **score**, and the proposed fix is grounded in the trajectory
    **shape** (which capabilities / phases the agent used), never in the missed gold.
  Descriptive dimensions (`pivot_burden`, `context_utilization`) are reported as *context* with
  ADR-0019's never-gated caveat — not as defects (no arbitrary thresholds invented).
- **No evaluator tampering (the other vector).** `reflect` proposes refinements to **ratified**
  artifacts (a skill, a query strategy, a mapping); it never edits eval scorers, gates,
  governance, or code — [ADR-0020](0020-adaptive-self-improving-ariadne.md)'s hard boundary.
- **Propose-only.** Output is `reflection.md` (human-readable) + `reflection.json` (structured
  findings + proposals), written beside the run's other artifacts. A human ratifies a proposed
  refinement before anything freezes — the human, not the agent, breaks the ICRH loop.
- **Deterministic core + `--llm`.** The deterministic diagnoser produces the structured, cited
  findings (it diagnoses; it does not author the verbal fix — the honest line, as B2's
  deterministic distiller records but does not generalize). `--llm` runs the reflexion move — a
  verbal post-mortem + a concrete proposed refinement per finding — via forced tool-use
  (`propose_reflection`), behind the `adaptive` extra + a key-guard, mirroring `ClaudeSkillDistiller`.

## Consequences

- B3 **closes the loop B2 opened**: B2 learns from success, B3 reflects on failure — the ExpeL
  success/failure contrast, both anchored on the *same* eval the loop may never edit.
- The two reward-hacking vectors are **structurally closed**: no scorer edits (a consequence of
  ADR-0020) and no gold reads (a consequence of the gold-free construction) — a statable safety
  property for an intelligence-analysis stakeholder.
- Propose-only keeps the human as the judgment/verification bottleneck (Anthropic's RSI framing)
  and breaks the deploy-time self-refine loop where reward hacking lives.
- A reflection carries the cited evidence for each finding, so a ratifier sees the basis inline —
  the citation ethos extended from notes (B-axis once more).
- Honest scoping (YAGNI): the first slice **diagnoses + proposes in prose**. Auto-regenerating a
  refined `SKILL.md` from a reflection, full ExpeL success-vs-failure rule mining, multi-run
  reflection, and the automated net-effect re-score (does the refinement out-score the original)
  are deferred — named, not built.

Sources: Reflexion — verbal reinforcement learning, episodic self-critique
([arXiv 2303.11366](https://arxiv.org/abs/2303.11366)); evaluation-integrity taxonomy —
evaluator tampering + train/test leakage ([arXiv 2603.11337](https://arxiv.org/pdf/2603.11337));
spontaneous reward hacking in iterative self-refinement
([arXiv 2407.04549](https://arxiv.org/pdf/2407.04549)) + in-context reward hacking
([arXiv 2402.06627](https://arxiv.org/pdf/2402.06627)); CRITIC tool-grounded self-correction and
ExpeL success/failure contrastive rules (the grounded-reflection lineage); the verifiability
constraint on intrinsic self-correction (self-correction reliable only with an external signal).
