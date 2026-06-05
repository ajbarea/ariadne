# Run-output organization — design

- **Date:** 2026-06-05
- **Status:** Approved (brainstorm) — implementation pending
- **ADR:** [0021](../../architecture/decisions/0021-run-output-organization.md)

## Problem

`ariadne workup` writes to `<out>/<entity-slug>/`, overwriting on re-run. We want
preserved, immutable, comparable runs across datasets and re-runs, each with a
reproducibility manifest — without building cross-run query/diff tooling.

## Goals / non-goals

**Goals:** never overwrite; human-browsable `runs/<dataset>/<entity>/<run-id>/`; a
`manifest.json` per run; a `latest` pointer; reader commands unchanged.

**Non-goals (YAGNI):** cross-run index, run diff/compare, eval-over-time dashboards,
run garbage-collection, content-addressed artifacts, a back-compat alias, a
symlink-less `latest` fallback (deferred until a native-Windows surface needs it).

## Run identity & layout

- Run id: `f"{now_utc:%Y-%m-%dT%H-%M-%SZ}-{trace8}"` — colons are already hyphenated,
  so the id is filesystem-safe. `trace8` = first 8 hex of the active OTel span's trace
  id, else `secrets.token_hex(4)`.
- Directory: `<out>/<dataset>/<slug>/<run-id>/`; default `<out>` = `runs/` (gitignored).
- `slug` = the existing `_slug()` (lowercased alphanumerics, others → `-`).
- `latest` symlink: `<out>/<dataset>/<slug>/latest → <run-id>` (relative), updated
  atomically (symlink to a temp name + `os.replace`).

## Manifest schema (`manifest.json`, run-dir root)

```json
{
  "run_id": "2026-06-05T18-23-01Z-4bf92f35",
  "entity": "Halberd",
  "dataset": "synthetic",
  "created_at": "2026-06-05T18:23:01Z",
  "otel_trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "ariadne_version": "0.1.0",
  "git_sha": "947f24e",
  "git_dirty": false,
  "model": "claude-opus-4-8",
  "profile": "default",
  "params": { "sql": true, "semantic": false, "entail": false, "strict": false },
  "duration_s": 42.7,
  "exit_code": 0,
  "scores": {
    "citations": { "ok": true, "uncited": 0, "dangling": 0, "unsupported": 0 },
    "tradecraft": { "nonstandard_terms": [] },
    "governance": { "ok": true },
    "eval": { "grounded": true, "recall": 1.0, "trajectory": 0.83 },
    "rubric": { "score": 4.5 }
  }
}
```

- `workup` writes the manifest with identity / provenance / params + the
  citations / tradecraft / governance scores + duration / exit_code it computes;
  `eval.*` and `rubric.*` are `null` until those commands run.
- `eval` / `rubric` read the manifest, **merge** their score block, and write it back.
  If `manifest.json` is absent (a foreign or legacy dir), they write their own `.json`
  as today and skip the merge (warn, never crash).

The schema is a deliberately lightweight **run-card**, not OpenLineage — the 2026
cross-tool lineage standard targets warehouse / orchestrator federation, which is YAGNI
for a single-binary CLI. `runs.py` carries the `# research(2026-06):` provenance for
that call and for the OTel-trace-in-manifest correlation pattern.

## Module boundary

A new `src/ariadne/runs.py` owns run identity, paths, the manifest, and `latest` —
one focused unit, testable without the agent loop:

- `run_id(now, trace_id) -> str` — pure; injectable clock + trace for tests.
- `run_dir(out_root, dataset, entity) -> Path` — pure path builder.
- `write_manifest(run_dir, manifest: Manifest) -> None`.
- `merge_scores(run_dir, scores: Mapping) -> None` — no-op-with-warning if absent.
- `update_latest(entity_dir, run_id) -> None` — atomic symlink replace.
- A frozen `Manifest` dataclass with `to_dict` / `from_dict`.

`cli.py` wiring:

- `workup`: compute `run_dir`, write all artifacts there, `write_manifest`,
  `update_latest`. Default `--out` root becomes `runs/`.
- `eval` / `rubric`: after writing their `.json`, call `merge_scores`.

## Back-compat

Clean break: workup's write location changes. The four reader commands already accept
an explicit directory, so they consume a run dir — or `latest` — unchanged (the OS
resolves the symlink). `.gitignore`: replace the `/workups/` line with `/runs/`.

## Testing (TDD, red→green)

- `run_id`: format regex; `trace8` derived from a supplied trace id; random fallback
  when none; two calls in the same second differ (suffix disambiguates).
- `run_dir`: composes `<out>/<dataset>/<slug>/<run-id>/` and reuses `_slug`.
- **No-overwrite property:** two workups (stub runner), same entity + dataset → two
  distinct dirs, both artifact sets intact.
- Manifest: round-trip `to_dict` / `from_dict`; `merge_scores` updates `scores.eval`
  without touching identity fields; absent-manifest merge is a no-op + warning.
- `latest`: resolves to the newest run; atomic replace over an existing symlink.
- Reader commands resolve both a run dir and a `latest` pointer (integration-light).

## After implementation

Run every dataset (`synthetic`, `enron`, `lahman`, `worldspeech`) into the new layout
— one preserved run each, metering the first to project cost. That is the motivating
use case, tracked separately from this feature.
