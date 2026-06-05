# Run-Output Organization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `ariadne workup` output from overwrite-in-place `<out>/<entity-slug>/` to immutable per-run directories `runs/<dataset>/<entity-slug>/<run-id>/`, each with a reproducibility `manifest.json` and a `latest` symlink.

**Architecture:** A new focused module `src/ariadne/runs.py` owns run identity, paths, the manifest, and `latest`. `cli.py`'s `run_workup` computes the run dir inside the existing `workup_span` (so the run id's trace8 suffix is the run's OTel trace), writes the manifest at the return (when the exit code is known), and updates `latest`; `eval`/`rubric` merge their scores into the same manifest. Clean break, no back-compat alias.

**Tech Stack:** Python 3.12, `opentelemetry-api` (base dep, no-op without SDK), `dataclasses`, `pytest`. Test runner: `uv run --no-active python -m pytest`. Whole-repo gate: `make lint`.

---

## File structure

- **Create** `src/ariadne/runs.py` — run identity (`slug`, `current_trace_hex`, `run_id`), path builder (`run_dir`), manifest (`Manifest`, `scores_from_reports`, `build_workup_manifest`, `write_manifest`, `read_manifest`, `merge_scores`), `latest` (`update_latest`), and `git_provenance`. One responsibility: how a run is named, recorded, and pointed at.
- **Create** `tests/unit/test_runs.py` — unit tests for every `runs.py` function.
- **Modify** `src/ariadne/cli.py` — import from `runs`; drop the local `_slug` (cli.py:592-593); wire `run_workup` (cli.py:540, 587-589) and the `--out` default (cli.py:71); call `merge_scores` in `_run_eval` (after cli.py:229) and `_run_rubric` (after cli.py:286).
- **Modify** `src/ariadne/mcp_server.py` — drop its duplicate `_slug` (mcp_server.py:33-34); import `slug` from `runs`.
- **Modify** `.gitignore` — replace `/workups/` with `/runs/`.

DRY note: `_slug` is currently duplicated verbatim in `cli.py` and `mcp_server.py`. Task 1 consolidates it into `runs.py`.

---

## Task 1: `slug()` in `runs.py` (DRY consolidation)

**Files:**
- Create: `src/ariadne/runs.py`
- Create: `tests/unit/test_runs.py`
- Modify: `src/ariadne/cli.py:592-593` (remove `_slug`, import `slug`), and its call sites `cli.py:355`, `cli.py:540`
- Modify: `src/ariadne/mcp_server.py:33-34` (remove `_slug`, import `slug`), and its call site `mcp_server.py:57`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_runs.py
from ariadne.runs import slug


def test_slug_lowercases_and_replaces_nonalnum():
    assert slug("Halberd") == "halberd"
    assert slug("vince.kaminski@enron.com") == "vince-kaminski-enron-com"


def test_slug_empty_falls_back_to_entity():
    assert slug("!!!") == "entity"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-active python -m pytest tests/unit/test_runs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ariadne.runs'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ariadne/runs.py
"""Run identity, paths, the per-run manifest, and the `latest` pointer (ADR-0021).

A workup's output is an immutable directory `runs/<dataset>/<slug>/<run-id>/`. This
module is the single owner of how that directory is named, recorded, and pointed at.
"""

from __future__ import annotations


def slug(entity: str) -> str:
    """Filesystem-safe entity key: lowercased alphanumerics, others -> '-'."""
    return "".join(c if c.isalnum() else "-" for c in entity).strip("-").lower() or "entity"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-active python -m pytest tests/unit/test_runs.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Replace the duplicated `_slug` at both call sites**

In `src/ariadne/cli.py`, delete the local definition (lines 592-593):

```python
def _slug(entity: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in entity).strip("-").lower() or "entity"
```

Add to the `ariadne.*` imports near the top of `cli.py`:

```python
from ariadne.runs import slug
```

Replace the two uses `_slug(entity)` (cli.py:355 and cli.py:540) with `slug(entity)`.

In `src/ariadne/mcp_server.py`, delete its `_slug` (lines 33-34). Its `write_subgraph` uses a local variable named `slug`, so import the function under an alias to avoid the shadow:

```python
from ariadne.runs import slug as entity_slug
# ...
slug = slug or entity_slug(entity)
```

- [ ] **Step 6: Run the whole suite + lint**

Run: `uv run --no-active python -m pytest tests/unit tests/test_smoke.py -q && make lint`
Expected: all pass (290+ tests), lint clean.

- [ ] **Step 7: Commit**

```bash
git add src/ariadne/runs.py tests/unit/test_runs.py src/ariadne/cli.py src/ariadne/mcp_server.py
git commit -m "refactor(runs): consolidate _slug into ariadne.runs (DRY)"
```

---

## Task 2: `current_trace_hex()` and `run_id()`

**Files:**
- Modify: `src/ariadne/runs.py`
- Modify: `tests/unit/test_runs.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_runs.py  (add)
from datetime import datetime, timezone

from ariadne.runs import run_id


def test_run_id_uses_trace_prefix_when_present():
    now = datetime(2026, 6, 5, 18, 23, 1, tzinfo=timezone.utc)
    rid = run_id(now, trace_hex="4bf92f3577b34da6a3ce929d0e0e4736")
    assert rid == "2026-06-05T18-23-01Z-4bf92f35"


def test_run_id_random_suffix_when_no_trace():
    now = datetime(2026, 6, 5, 18, 23, 1, tzinfo=timezone.utc)
    a = run_id(now, trace_hex="")
    b = run_id(now, trace_hex="")
    assert a.startswith("2026-06-05T18-23-01Z-")
    assert len(a.rsplit("-", 1)[1]) == 8
    assert a != b  # random suffix disambiguates same-second runs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-active python -m pytest tests/unit/test_runs.py -k run_id -v`
Expected: FAIL — `ImportError: cannot import name 'run_id'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ariadne/runs.py  (add imports + functions)
import secrets
from datetime import datetime

from opentelemetry import trace


def current_trace_hex() -> str:
    """The active span's 32-hex trace id, or "" when no recording span is active.

    research(2026-06): the validated way to tie an output artifact to its run is to
    embed the OTel trace context into the run's metadata (and here, its id). With only
    opentelemetry-api (no SDK/exporter), trace_id is 0 -> "" -> random suffix.
    """
    ctx = trace.get_current_span().get_span_context()
    return f"{ctx.trace_id:032x}" if ctx.trace_id else ""


def run_id(now: datetime, trace_hex: str = "") -> str:
    """`<UTC, colons->hyphens>Z-<suffix>`; suffix = trace8 if present else 8 random hex."""
    suffix = trace_hex[:8] if trace_hex else secrets.token_hex(4)
    return f"{now:%Y-%m-%dT%H-%M-%S}Z-{suffix}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-active python -m pytest tests/unit/test_runs.py -k run_id -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ariadne/runs.py tests/unit/test_runs.py
git commit -m "feat(runs): run_id (UTC timestamp + OTel trace8 / random suffix)"
```

---

## Task 3: `run_dir()` path builder

**Files:**
- Modify: `src/ariadne/runs.py`
- Modify: `tests/unit/test_runs.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_runs.py  (add)
from pathlib import Path

from ariadne.runs import run_dir


def test_run_dir_composes_dataset_slug_runid():
    now = datetime(2026, 6, 5, 18, 23, 1, tzinfo=timezone.utc)
    d = run_dir("runs", "synthetic", "Halberd", now=now, trace_hex="4bf92f35aaaaaaaa")
    assert d == Path("runs/synthetic/halberd/2026-06-05T18-23-01Z-4bf92f35")


def test_run_dir_two_calls_never_collide():
    now = datetime(2026, 6, 5, 18, 23, 1, tzinfo=timezone.utc)
    a = run_dir("runs", "synthetic", "Halberd", now=now)  # no trace -> random suffix
    b = run_dir("runs", "synthetic", "Halberd", now=now)
    assert a != b  # the no-overwrite property
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-active python -m pytest tests/unit/test_runs.py -k run_dir -v`
Expected: FAIL — `ImportError: cannot import name 'run_dir'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ariadne/runs.py  (add import + function)
from datetime import timezone
from pathlib import Path


def run_dir(
    out_root: str | Path,
    dataset: str,
    entity: str,
    *,
    now: datetime | None = None,
    trace_hex: str = "",
) -> Path:
    """Pure path: `<out_root>/<dataset>/<slug>/<run-id>/`. Does not touch the disk."""
    now = now or datetime.now(timezone.utc)
    return Path(out_root) / dataset / slug(entity) / run_id(now, trace_hex)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-active python -m pytest tests/unit/test_runs.py -k run_dir -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ariadne/runs.py tests/unit/test_runs.py
git commit -m "feat(runs): run_dir path builder (dataset/slug/run-id)"
```

---

## Task 4: `Manifest`, `scores_from_reports()`, `build_workup_manifest()`

**Files:**
- Modify: `src/ariadne/runs.py`
- Modify: `tests/unit/test_runs.py`

Score sources (confirmed in code): `CitationReport` has `.ok: bool`, `.dangling/.uncited/.unsupported: list[str]`; `TradecraftReport` has `.nonstandard_terms`; `GovernanceReport` has `.ok: bool`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_runs.py  (add)
from dataclasses import dataclass

from ariadne.runs import Manifest, scores_from_reports


@dataclass
class _Cite:
    ok: bool = True
    dangling: list = None
    uncited: list = None
    unsupported: list = None


@dataclass
class _Trade:
    nonstandard_terms: list = None


@dataclass
class _Gov:
    ok: bool = True


def test_scores_from_reports_shapes_the_block():
    s = scores_from_reports(
        _Cite(ok=True, dangling=[], uncited=["x"], unsupported=[]),
        _Trade(nonstandard_terms=["likely"]),
        _Gov(ok=True),
    )
    assert s["citations"] == {"ok": True, "uncited": 1, "dangling": 0, "unsupported": 0}
    assert s["tradecraft"] == {"nonstandard_terms": ["likely"]}
    assert s["governance"] == {"ok": True}
    assert s["eval"] is None and s["rubric"] is None


def test_manifest_round_trips():
    m = Manifest(
        run_id="2026-06-05T18-23-01Z-4bf92f35",
        entity="Halberd",
        dataset="synthetic",
        created_at="2026-06-05T18:23:01Z",
        otel_trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
        ariadne_version="0.1.0",
        git_sha="947f24e",
        git_dirty=False,
        model="claude-opus-4-8",
        profile="default",
        params={"sql": True, "semantic": False, "entail": False, "strict": False},
        duration_s=42.7,
        exit_code=0,
        scores={"citations": {"ok": True}, "eval": None, "rubric": None},
    )
    assert Manifest.from_dict(m.to_dict()) == m
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-active python -m pytest tests/unit/test_runs.py -k "scores or manifest" -v`
Expected: FAIL — `ImportError: cannot import name 'Manifest'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ariadne/runs.py  (add)
from collections.abc import Mapping
from dataclasses import asdict, dataclass


def scores_from_reports(citations, tradecraft, governance) -> dict:
    """The manifest `scores` block at workup time; eval/rubric are filled in later."""
    return {
        "citations": {
            "ok": citations.ok,
            "uncited": len(citations.uncited),
            "dangling": len(citations.dangling),
            "unsupported": len(citations.unsupported),
        },
        "tradecraft": {"nonstandard_terms": sorted(set(tradecraft.nonstandard_terms))},
        "governance": {"ok": governance.ok},
        "eval": None,
        "rubric": None,
    }


@dataclass(frozen=True)
class Manifest:
    """The per-run reproducibility record (ADR-0021). One file = the whole run.

    research(2026-06): a deliberately lightweight run-card, not OpenLineage (the 2026
    cross-tool lineage standard) — that targets warehouse/orchestrator federation,
    YAGNI for a single-binary CLI. We borrow its run-metadata vocabulary only.
    """

    run_id: str
    entity: str
    dataset: str
    created_at: str
    otel_trace_id: str | None
    ariadne_version: str
    git_sha: str
    git_dirty: bool
    model: str | None
    profile: str
    params: dict
    duration_s: float
    exit_code: int
    scores: dict

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping) -> Manifest:
        return cls(**data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-active python -m pytest tests/unit/test_runs.py -k "scores or manifest" -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ariadne/runs.py tests/unit/test_runs.py
git commit -m "feat(runs): Manifest record + scores_from_reports"
```

---

## Task 5: `write_manifest()` / `read_manifest()`

**Files:**
- Modify: `src/ariadne/runs.py`
- Modify: `tests/unit/test_runs.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_runs.py  (add)
from ariadne.runs import read_manifest, write_manifest


def _manifest(**over):
    base = dict(
        run_id="r", entity="Halberd", dataset="synthetic", created_at="t",
        otel_trace_id=None, ariadne_version="0.1.0", git_sha="abc", git_dirty=False,
        model=None, profile="default", params={}, duration_s=1.0, exit_code=0,
        scores={"eval": None},
    )
    base.update(over)
    return Manifest(**base)


def test_write_then_read_manifest(tmp_path):
    write_manifest(tmp_path, _manifest())
    assert (tmp_path / "manifest.json").is_file()
    assert read_manifest(tmp_path)["entity"] == "Halberd"


def test_read_manifest_absent_returns_none(tmp_path):
    assert read_manifest(tmp_path) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-active python -m pytest tests/unit/test_runs.py -k manifest_ -v`
Expected: FAIL — `ImportError: cannot import name 'write_manifest'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ariadne/runs.py  (add)
import json

_MANIFEST = "manifest.json"


def write_manifest(run_directory: Path, manifest: Manifest) -> None:
    run_directory.mkdir(parents=True, exist_ok=True)
    (run_directory / _MANIFEST).write_text(
        json.dumps(manifest.to_dict(), indent=2), encoding="utf-8"
    )


def read_manifest(run_directory: Path) -> dict | None:
    path = run_directory / _MANIFEST
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-active python -m pytest tests/unit/test_runs.py -k manifest_ -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ariadne/runs.py tests/unit/test_runs.py
git commit -m "feat(runs): write/read manifest.json"
```

---

## Task 6: `merge_scores()` (no-op when absent)

**Files:**
- Modify: `src/ariadne/runs.py`
- Modify: `tests/unit/test_runs.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_runs.py  (add)
from ariadne.runs import merge_scores


def test_merge_scores_updates_eval_without_touching_identity(tmp_path):
    write_manifest(tmp_path, _manifest(scores={"citations": {"ok": True}, "eval": None}))
    merge_scores(tmp_path, {"eval": {"grounded": True, "recall": 1.0, "trajectory": 0.8}})
    data = read_manifest(tmp_path)
    assert data["entity"] == "Halberd"  # identity untouched
    assert data["scores"]["eval"] == {"grounded": True, "recall": 1.0, "trajectory": 0.8}
    assert data["scores"]["citations"] == {"ok": True}  # existing block preserved


def test_merge_scores_absent_manifest_is_noop(tmp_path, capsys):
    merge_scores(tmp_path, {"eval": {"grounded": True}})  # must not raise
    assert not (tmp_path / "manifest.json").exists()
    assert "manifest" in capsys.readouterr().err.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-active python -m pytest tests/unit/test_runs.py -k merge_scores -v`
Expected: FAIL — `ImportError: cannot import name 'merge_scores'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ariadne/runs.py  (add import + function)
import sys


def merge_scores(run_directory: Path, scores: Mapping) -> None:
    """Merge a score block (e.g. {"eval": {...}}) into an existing manifest's scores.

    No-op (with a stderr warning) when there is no manifest — e.g. a foreign or legacy
    dir — so eval/rubric never crash on a run they did not write.
    """
    data = read_manifest(run_directory)
    if data is None:
        print(
            f"No manifest.json in {run_directory} — skipping score merge.", file=sys.stderr
        )
        return
    data.setdefault("scores", {}).update(scores)
    (run_directory / _MANIFEST).write_text(json.dumps(data, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-active python -m pytest tests/unit/test_runs.py -k merge_scores -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ariadne/runs.py tests/unit/test_runs.py
git commit -m "feat(runs): merge_scores into manifest (no-op if absent)"
```

---

## Task 7: `update_latest()` atomic symlink

**Files:**
- Modify: `src/ariadne/runs.py`
- Modify: `tests/unit/test_runs.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_runs.py  (add)
import os

from ariadne.runs import update_latest


def test_update_latest_points_at_run(tmp_path):
    entity_dir = tmp_path / "synthetic" / "halberd"
    (entity_dir / "run-a").mkdir(parents=True)
    update_latest(entity_dir, "run-a")
    link = entity_dir / "latest"
    assert link.is_symlink() and os.readlink(link) == "run-a"


def test_update_latest_replaces_existing(tmp_path):
    entity_dir = tmp_path / "synthetic" / "halberd"
    (entity_dir / "run-a").mkdir(parents=True)
    (entity_dir / "run-b").mkdir()
    update_latest(entity_dir, "run-a")
    update_latest(entity_dir, "run-b")
    assert os.readlink(entity_dir / "latest") == "run-b"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-active python -m pytest tests/unit/test_runs.py -k update_latest -v`
Expected: FAIL — `ImportError: cannot import name 'update_latest'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ariadne/runs.py  (add)
def update_latest(entity_dir: Path, run_id_name: str) -> None:
    """Atomically point `<entity_dir>/latest` at the run dir `run_id_name` (relative)."""
    tmp = entity_dir / f".latest.{secrets.token_hex(4)}"
    os.symlink(run_id_name, tmp, target_is_directory=True)
    os.replace(tmp, entity_dir / "latest")  # atomic swap over any existing symlink
```

Add `import os` to the module imports.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-active python -m pytest tests/unit/test_runs.py -k update_latest -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ariadne/runs.py tests/unit/test_runs.py
git commit -m "feat(runs): update_latest atomic symlink"
```

---

## Task 8: `git_provenance()` and `build_workup_manifest()`

**Files:**
- Modify: `src/ariadne/runs.py`
- Modify: `tests/unit/test_runs.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_runs.py  (add)
from ariadne.runs import build_workup_manifest, git_provenance


def test_git_provenance_returns_sha_and_dirty_flag():
    sha, dirty = git_provenance()
    assert isinstance(sha, str) and sha  # "unknown" or a short hash, never empty
    assert isinstance(dirty, bool)


def test_build_workup_manifest_assembles_record():
    m = build_workup_manifest(
        run_directory=Path("runs/synthetic/halberd/2026-06-05T18-23-01Z-4bf92f35"),
        entity="Halberd",
        dataset="synthetic",
        model="claude-opus-4-8",
        profile="default",
        params={"sql": True, "semantic": False, "entail": False, "strict": False},
        duration_s=42.7,
        exit_code=0,
        trace_hex="4bf92f3577b34da6a3ce929d0e0e4736",
        scores={"citations": {"ok": True}, "eval": None, "rubric": None},
    )
    assert m.run_id == "2026-06-05T18-23-01Z-4bf92f35"
    assert m.otel_trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert m.created_at.endswith("Z")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-active python -m pytest tests/unit/test_runs.py -k "git_provenance or build_workup" -v`
Expected: FAIL — `ImportError: cannot import name 'build_workup_manifest'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ariadne/runs.py  (add)
import subprocess

from ariadne import __version__


def git_provenance() -> tuple[str, bool]:
    """`(short_sha, dirty)`; `("unknown", False)` when git is unavailable."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
        )
        return sha or "unknown", dirty
    except (OSError, subprocess.CalledProcessError):
        return "unknown", False


def build_workup_manifest(
    *,
    run_directory: Path,
    entity: str,
    dataset: str,
    model: str | None,
    profile: str,
    params: dict,
    duration_s: float,
    exit_code: int,
    trace_hex: str,
    scores: dict,
) -> Manifest:
    """Assemble the run record from what `run_workup` knows at the return."""
    sha, dirty = git_provenance()
    return Manifest(
        run_id=run_directory.name,
        entity=entity,
        dataset=dataset,
        created_at=f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%S}Z",
        otel_trace_id=trace_hex or None,
        ariadne_version=__version__,
        git_sha=sha,
        git_dirty=dirty,
        model=model,
        profile=profile,
        params=params,
        duration_s=duration_s,
        exit_code=exit_code,
        scores=scores,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-active python -m pytest tests/unit/test_runs.py -k "git_provenance or build_workup" -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ariadne/runs.py tests/unit/test_runs.py
git commit -m "feat(runs): git_provenance + build_workup_manifest"
```

---

## Task 9: Wire `run_workup` + change the `--out` default

**Files:**
- Modify: `src/ariadne/cli.py:71` (`--out` default), `cli.py:540` (run dir), `cli.py:587-589` (return: manifest + latest)

This task sequences already-tested `runs.py` units; verification is the full unit suite (no regressions) plus a real workup smoke (Task 11).

- [ ] **Step 1: Add the imports**

In `cli.py`, extend the `from ariadne.runs import slug` line (added in Task 1) to:

```python
from ariadne.runs import (
    build_workup_manifest,
    current_trace_hex,
    run_dir,
    scores_from_reports,
    slug,
    update_latest,
    write_manifest,
)
```

- [ ] **Step 2: Change the `--out` default (cli.py:71)**

```python
wk.add_argument("--out", default="runs", help="Run-output root (runs/<dataset>/<entity>/<run-id>/)")
```

- [ ] **Step 3: Compute the run dir inside the span (replace cli.py:540)**

Replace:

```python
        out_dir = Path(out_root) / _slug(entity)
```

with (capture the trace hex once, inside `workup_span`, for both the id suffix and the manifest):

```python
        trace_hex = current_trace_hex()
        out_dir = run_dir(out_root, dataset, entity, trace_hex=trace_hex)
```

- [ ] **Step 4: Write the manifest + latest at the return (replace cli.py:587-589)**

Replace:

```python
    return workup_exit_code(
        governance=governance, strict=strict, had_error=had_error, citations_ok=report.ok
    )
```

with:

```python
    code = workup_exit_code(
        governance=governance, strict=strict, had_error=had_error, citations_ok=report.ok
    )
    write_manifest(
        out_dir,
        build_workup_manifest(
            run_directory=out_dir,
            entity=entity,
            dataset=dataset,
            model=prof.model,
            profile=prof.name,
            params={
                "sql": with_sql,
                "semantic": with_semantic,
                "entail": with_entail,
                "strict": strict,
            },
            duration_s=elapsed,
            exit_code=code,
            trace_hex=trace_hex,
            scores=scores_from_reports(report, tradecraft, governance),
        ),
    )
    update_latest(out_dir.parent, out_dir.name)
    return code
```

(`out_dir`, `trace_hex`, `elapsed`, `report`, `tradecraft`, `governance`, `prof` remain in scope after the `with workup_span(...)` block — Python `with` does not create a new scope.)

- [ ] **Step 5: Run the suite + lint**

Run: `uv run --no-active python -m pytest tests/unit tests/test_smoke.py -q && make lint`
Expected: all pass, lint clean. (`Path` import in cli.py is still used elsewhere; leave it.)

- [ ] **Step 6: Commit**

```bash
git add src/ariadne/cli.py
git commit -m "feat(workup): write to runs/<dataset>/<entity>/<run-id>/ with manifest + latest"
```

---

## Task 10: Merge eval/rubric scores into the manifest

**Files:**
- Modify: `src/ariadne/cli.py` — `_run_eval` (after cli.py:229), `_run_rubric` (after cli.py:286)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_runs.py  (add) — exercises the wiring contract via merge_scores
def test_eval_score_block_shape(tmp_path):
    """The block _run_eval merges must land under scores.eval with these keys."""
    write_manifest(tmp_path, _manifest(scores={"eval": None, "rubric": None}))
    merge_scores(tmp_path, {"eval": {"grounded": True, "recall": 1.0, "trajectory": 0.83}})
    assert set(read_manifest(tmp_path)["scores"]["eval"]) == {"grounded", "recall", "trajectory"}
```

- [ ] **Step 2: Run test to verify it fails, then passes**

Run: `uv run --no-active python -m pytest tests/unit/test_runs.py -k eval_score_block -v`
Expected: PASS already (merge_scores exists) — this pins the block shape the wiring must emit. If it errors, fix `merge_scores` first.

- [ ] **Step 3: Wire `_run_eval`** — after `write_eval_json(...)` (cli.py:229), add:

```python
        merge_scores(
            Path(workup_dir),
            {
                "eval": {
                    "grounded": report.grounded,
                    "recall": report.recall,
                    "trajectory": report.trajectory,
                }
            },
        )
```

Add `merge_scores` to the `from ariadne.runs import (...)` block.

- [ ] **Step 4: Wire `_run_rubric`** — after `write_rubric_json(workup_dir, report)` (cli.py:286), add:

```python
    merge_scores(Path(workup_dir), {"rubric": {"score": report.overall}})
```

- [ ] **Step 5: Run the suite + lint**

Run: `uv run --no-active python -m pytest tests/unit tests/test_smoke.py -q && make lint`
Expected: all pass, lint clean.

- [ ] **Step 6: Commit**

```bash
git add src/ariadne/cli.py tests/unit/test_runs.py
git commit -m "feat(eval,rubric): merge scores into the run manifest"
```

---

## Task 11: `.gitignore` swap + live smoke

**Files:**
- Modify: `.gitignore:19-20`

- [ ] **Step 1: Swap the ignore rule**

Replace `.gitignore` lines 19-20:

```
# Workup run artifacts (CLI default --out ./workups; analytic notes + provenance)
/workups/
```

with:

```
# Run artifacts (CLI default --out runs/; immutable per-run dirs + manifest, ADR-0021)
/runs/
```

- [ ] **Step 2: Live smoke (needs ANTHROPIC_API_KEY + the seeded stack)**

Run:

```bash
env -u ANTHROPIC_BASE_URL uv run --no-active ariadne workup Halberd --dataset synthetic --sql
ls runs/synthetic/halberd/
cat runs/synthetic/halberd/latest/manifest.json
```

Expected: a `runs/synthetic/halberd/<run-id>/` dir + a `latest` symlink; `manifest.json` shows identity, provenance, `scores.citations`, `scores.eval == null`. Then:

```bash
env -u ANTHROPIC_BASE_URL uv run --no-active ariadne eval runs/synthetic/halberd/latest --reconcile synthetic
```

Expected: `manifest.json`'s `scores.eval` is now populated; `git status` shows `runs/` is untracked-and-ignored.

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore(gitignore): ignore /runs/ (ADR-0021), drop /workups/"
```

---

## Self-Review

**Spec coverage:** never-overwrite (Task 3 `test_run_dir_two_calls_never_collide`); layout `runs/<dataset>/<slug>/<run-id>/` (Task 3, 9); run id timestamp+trace8/random (Task 2); manifest schema + lifecycle (Tasks 4-6, 9, 10); `latest` symlink (Task 7, 9); reader commands unchanged + merge (Task 10); default `--out`=`runs/` (Task 9); gitignore swap (Task 11); OpenLineage-rejection + trace-correlation research comments (Tasks 2, 4). All spec sections map to a task.

**Placeholder scan:** none — every step has runnable code or an exact command.

**Type consistency:** `slug`, `run_id(now, trace_hex)`, `run_dir(..., now=, trace_hex=)`, `Manifest(...)` fields, `scores_from_reports`, `build_workup_manifest(*, run_directory=, ...)`, `merge_scores(run_directory, scores)`, `update_latest(entity_dir, run_id_name)`, `current_trace_hex` — names and signatures are used identically across Tasks 1-11.
