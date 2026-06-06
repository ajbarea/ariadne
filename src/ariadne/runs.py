"""Run identity, paths, the per-run manifest, and the `latest` pointer (ADR-0021).

A workup's output is an immutable directory `runs/<dataset>/<slug>/<run-id>/`. This
module is the single owner of how that directory is named, recorded, and pointed at.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from pathlib import Path

from opentelemetry import trace


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
