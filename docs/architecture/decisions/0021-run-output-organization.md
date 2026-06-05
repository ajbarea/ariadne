# 0021, Run-output organization — immutable per-run directories with a reproducibility manifest

- **Status:** Accepted (2026-06-05)
- **Deciders:** Ariadne maintainers

## Context

`ariadne workup` writes its artifacts to `<out>/<entity-slug>/` — e.g.
`./workups/halberd/`. The directory is keyed only by a slug of the entity name, so
re-running the same entity **overwrites** the prior run's `note.md`, `report.html`,
and the JSON sidecars in place. There is no run identifier, no timestamp, and no
record of *how* a run was produced (model, profile, code version, flags). Different
entities coexist; the same entity clobbers.

This blocks what we now want: preserving multiple runs — across datasets and across
re-runs of one entity — so they can be compared, and so a demo's outputs survive the
next invocation. It is also below the 2026 baseline for run artifacts.

Ariadne is already most of the way there: every workup emits a `provenance.jsonl`
ledger and OpenTelemetry traces, and produces `eval.json` / `rubric.json` post-hoc.
What is missing is the *run-isolation* layer — a run identity, a manifest, and the
discipline of never overwriting.

## Decision drivers

- **Never overwrite.** Every run is immutable; a re-run is a new directory.
- **Human-browsable.** The maintainer inspects runs with `ls` and a file tree, so
  the layout and the run id must be legible at a glance, not merely machine-sortable.
- **Reproducibility-grade, not experiment-tracking.** Capture enough per run to
  reproduce and compare it (model, profile, git SHA, params, scores) — but *not* a
  cross-run index or diff tooling (YAGNI for a single-maintainer prototype).
- **Reuse what already exists.** `provenance.jsonl`, the OTel trace, and the
  eval/rubric scores are already produced; the manifest captures them, not recompute.
- **Lean on the OTel trace for provenance linkage.** An agentic run already has a
  trace identity; the run directory should reconcile with it — 2026 agentic-artifact
  practice ties each run to its provenance trace.
- **Clean break.** Pre-release, single maintainer: replace the old write path, do
  not carry a back-compat alias.

## Considered options

### Run identifier

1. **UTC timestamp + 8-hex OTel trace prefix** — `2026-06-05T18-23-01Z-4bf92f35`.
   *Chosen.* Human-readable wall clock (sortable, legible in `ls`) **and** a suffix
   that is the first 8 hex of the run's OpenTelemetry trace id — so the folder name
   is itself a handle into the trace and the provenance ledger. Collision-safe (the
   suffix disambiguates same-second runs). Falls back to 8 random hex when no trace
   is active; the full 32-hex trace id is always recorded in the manifest.
2. **ULID** — `01J9Z3K8QH7M...`. *Rejected.* Lexicographically sortable and unique,
   but the embedded time is not eyeball-able without decoding — it fails the
   human-browsable driver.
3. **Pure OTel trace id** — `4bf92f3577b34da6...` (32 hex). *Rejected.* Maximal trace
   unification, but fully opaque (no readable time) and it couples run identity to
   tracing being active. We keep the *linkage* (trace prefix in the name, full id in
   the manifest) without paying the legibility cost.

### Layout

4. **`runs/<dataset>/<entity-slug>/<run-id>/`** — *Chosen.* Groups by corpus first,
   so each dataset is a clean subtree and "did it work on every dataset" is visible
   at a glance; within a dataset, an entity's re-runs sit together.
5. **`runs/<entity-slug>/<run-id>/`** — *Rejected.* Better for hammering one entity
   across corpora, but mixes datasets and obscures coverage — the wrong optimization
   for the immediate multi-dataset goal.
6. **Flat `runs/<run-id>/`** — *Rejected.* Simplest tree, but pushes all navigation
   into manifests and loses the at-a-glance dataset/entity grouping.

### Scope

7. **Per-run manifest only** — *Chosen.* A `manifest.json` per run is the
   reproducibility record.
8. **Cross-run index + diff/compare tooling** — *Deferred (YAGNI).* Querying and
   diffing runs is real experiment-tracking; revisit if comparing-by-hand becomes the
   bottleneck.
9. **Adopt OpenLineage Run/Job/Dataset facets for the manifest** — *Rejected (YAGNI).*
   OpenLineage ([openlineage.io](https://openlineage.io/getting-started/)) is the 2026
   cross-tool lineage-federation standard for warehouse / orchestrator / catalog stacks
   — built to federate metadata *across tools*, not to describe a single-binary CLI's
   local run dirs. We borrow its run-metadata vocabulary (a run timestamp ≈
   `nominalTime`, a git commit hash, a config snapshot) in a lightweight run-card
   manifest, without the facet schema or an emitter.

## Decision

- Workup output moves to **`runs/<dataset>/<entity-slug>/<run-id>/`**, run id
  **`<UTC ISO, colons→hyphens>Z-<trace8>`**, default `--out` root `runs/` (gitignored;
  `--out` still overrides).
- Each run carries a **`manifest.json`**: identity (run_id, entity, dataset,
  created_at, otel_trace_id), provenance (ariadne_version, git_sha + dirty, model,
  profile, cli params), and outcome (duration_s, exit_code, and a `scores` block —
  citations / tradecraft / governance written by `workup`, eval / rubric merged in by
  those commands when they run). One file is the whole run record.
- A **`latest`** symlink per entity (`runs/<dataset>/<slug>/latest → <run-id>/`) points
  at the most recent run, updated atomically. The four reader commands (`report` /
  `eval` / `governance` / `rubric`) already take an explicit directory, so they consume
  a run dir — or `latest` — with no change (the OS resolves the symlink).
- **Clean break:** the flat `<out>/<slug>/` write path is replaced, not aliased.

## Consequences

- Runs are preserved, immutable, and comparable; a demo's outputs survive the next
  workup, and "test every dataset" yields a legible coverage tree.
- The manifest makes each run reproducible and self-describing, reusing artifacts
  Ariadne already emits — a small, honest increment, no new scoring.
- The run directory reconciles with its OTel trace and provenance ledger via the
  trace8 prefix, without an opaque directory name.
- **Costs:** disk grows monotonically (no run GC yet — a future `ariadne runs gc` if
  it bites); `latest` is a symlink (fine on the WSL/macOS dev surface; a native-Windows
  checkout would need a file-pointer fallback, deferred until that surface matters); the clean break
  invalidates muscle-memory of `./workups/<slug>/` paths.

Sources: Hydra run-directory convention and Hydra×MLflow output organization
([tnwei](https://tnwei.github.io/posts/mlflow-x-hydra/),
[lightning-hydra-template](https://github.com/ashleve/lightning-hydra-template)); MLflow
run-id / artifact model ([mlflow.org](https://mlflow.org/docs/latest/tracking/));
immutable, provenance-linked LLM-agent artifacts, 2026
([Nexxen](https://nexxen.com/building-an-artifacts-system-for-our-llm-data-agents/),
[agentic architecture playbook](https://dstreefkerk.github.io/2026-02-agentic-architecture-playbook-patterns-for-reliable-llm-workflows/),
[Cloudsmith LLMOps](https://cloudsmith.com/blog/llmops-vs-devops-what-llmops-means-for-artifact-management)).
