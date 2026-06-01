"""Persist a workup run's artifacts to an output directory."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ariadne.provenance.citations import CitationReport  # noqa: TC001
from ariadne.provenance.ledger import ProvenanceLedger  # noqa: TC001


def write_outputs(
    out_dir: str | Path,
    *,
    entity: str,
    note: str,
    ledger: ProvenanceLedger,
    report: CitationReport,
) -> None:
    """Write ``note.md``, ``provenance.jsonl`` and ``citations.json`` to ``out_dir``."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "note.md").write_text(note, encoding="utf-8")
    ledger.write_jsonl(out_dir / "provenance.jsonl")
    payload = {"entity": entity, **asdict(report)}
    (out_dir / "citations.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
