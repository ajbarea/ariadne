"""Run identity, paths, the per-run manifest, and the `latest` pointer (ADR-0021).

A workup's output is an immutable directory `runs/<dataset>/<slug>/<run-id>/`. This
module is the single owner of how that directory is named, recorded, and pointed at.
"""

from __future__ import annotations

import json
import secrets
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from opentelemetry import trace

from ariadne import __version__

if TYPE_CHECKING:
    from collections.abc import Mapping

_MANIFEST = "manifest.json"


def slug(entity: str) -> str:
    """Filesystem-safe entity key: lowercased alphanumerics, others -> '-'."""
    return "".join(c if c.isalnum() else "-" for c in entity).strip("-").lower() or "entity"


def current_trace_hex() -> str:
    """The active span's 32-hex trace id, or "" when no recording span is active.

    research(2026-06): the validated way to tie an output artifact to its run is to
    embed the OTel trace context into the run's metadata (and here, its id). With only
    opentelemetry-api (no SDK/exporter) trace_id is 0 -> "" -> random suffix.
    """
    ctx = trace.get_current_span().get_span_context()
    return f"{ctx.trace_id:032x}" if ctx.trace_id else ""


def run_id(now: datetime, trace_hex: str = "") -> str:
    """`<UTC, colons->hyphens>Z-<suffix>`; suffix = trace8 if present else 8 random hex."""
    suffix = trace_hex[:8] if trace_hex else secrets.token_hex(4)
    return f"{now:%Y-%m-%dT%H-%M-%S}Z-{suffix}"


def run_dir(
    out_root: str | Path,
    dataset: str,
    entity: str,
    *,
    now: datetime | None = None,
    trace_hex: str = "",
) -> Path:
    """Pure path: `<out_root>/<dataset>/<slug>/<run-id>/`. Does not touch the disk."""
    now = now or datetime.now(UTC)
    return Path(out_root) / dataset / slug(entity) / run_id(now, trace_hex)


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
    cost_usd: float | None
    usage: dict | None
    scores: dict
    # The skills the agent invoked this run (ADR-0034's SkillTester gate reads this).
    # None on a legacy run written before recording was wired = "instrument absent"
    # (unobserved); [] = "recorded, none fired" — the gate treats them differently.
    skills_invoked: list[str] | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping) -> Manifest:
        return cls(**data)


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


def merge_scores(run_directory: Path, scores: Mapping) -> None:
    """Merge a score block (e.g. {"eval": {...}}) into an existing manifest's scores.

    No-op (with a stderr warning) when there is no manifest — e.g. a foreign or legacy
    dir — so eval/rubric never crash on a run they did not write.
    """
    data = read_manifest(run_directory)
    if data is None:
        print(f"No manifest at {run_directory}; skipping merge.", file=sys.stderr)  # noqa: T201
        return
    data.setdefault("scores", {}).update(scores)
    (run_directory / _MANIFEST).write_text(json.dumps(data, indent=2), encoding="utf-8")


def update_latest(entity_dir: Path, run_id_name: str) -> None:
    """Atomically point `<entity_dir>/latest` at the run dir `run_id_name` (relative)."""
    tmp = entity_dir / f".latest.{secrets.token_hex(4)}"
    tmp.symlink_to(run_id_name, target_is_directory=True)
    tmp.replace(entity_dir / "latest")  # atomic swap over any existing symlink


def _git(*args: str) -> str:
    """Run `git <args>` and return stripped stdout. Inputs are internal literals
    (rev-parse / status), never user data — S603 is suppressed accordingly."""
    cmd = ["git", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)  # noqa: S603
    return proc.stdout.strip()


def git_provenance() -> tuple[str, bool]:
    """`(short_sha, dirty)`; `("unknown", False)` when git is unavailable."""
    try:
        sha = _git("rev-parse", "--short", "HEAD")
        dirty = bool(_git("status", "--porcelain"))
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
    cost_usd: float | None = None,
    usage: dict | None = None,
    skills_invoked: list[str] | None = None,
) -> Manifest:
    """Assemble the run record from what `run_workup` knows at the return."""
    sha, dirty = git_provenance()
    return Manifest(
        run_id=run_directory.name,
        entity=entity,
        dataset=dataset,
        created_at=f"{datetime.now(UTC):%Y-%m-%dT%H:%M:%S}Z",
        otel_trace_id=trace_hex or None,
        ariadne_version=__version__,
        git_sha=sha,
        git_dirty=dirty,
        model=model,
        profile=profile,
        params=params,
        duration_s=duration_s,
        exit_code=exit_code,
        cost_usd=cost_usd,
        usage=usage,
        scores=scores,
        skills_invoked=skills_invoked,
    )
