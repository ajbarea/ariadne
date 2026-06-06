"""Run identity, paths, the per-run manifest, and the `latest` pointer (ADR-0021).

A workup's output is an immutable directory `runs/<dataset>/<slug>/<run-id>/`. This
module is the single owner of how that directory is named, recorded, and pointed at.
"""

from __future__ import annotations


def slug(entity: str) -> str:
    """Filesystem-safe entity key: lowercased alphanumerics, others -> '-'."""
    return "".join(c if c.isalnum() else "-" for c in entity).strip("-").lower() or "entity"
