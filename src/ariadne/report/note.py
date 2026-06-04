"""Persist a workup run's artifacts to an output directory."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ariadne.profiles import Profile  # noqa: TC001
from ariadne.provenance.citations import CitationReport  # noqa: TC001
from ariadne.provenance.governance import GovernanceReport  # noqa: TC001
from ariadne.provenance.ledger import ProvenanceLedger  # noqa: TC001
from ariadne.provenance.tradecraft import TradecraftReport  # noqa: TC001


def write_outputs(
    out_dir: str | Path,
    *,
    entity: str,
    note: str,
    ledger: ProvenanceLedger,
    report: CitationReport,
    tradecraft: TradecraftReport | None = None,
    governance: GovernanceReport | None = None,
    profile: Profile | None = None,
) -> None:
    """Write ``note.md``, ``provenance.jsonl``, ``citations.json`` (and, when supplied,
    the advisory ``tradecraft.json`` / ``governance.json``) to ``out_dir``."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "note.md").write_text(note, encoding="utf-8")
    ledger.write_jsonl(out_dir / "provenance.jsonl")
    payload = {"entity": entity, **asdict(report)}
    (out_dir / "citations.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if tradecraft is not None:
        (out_dir / "tradecraft.json").write_text(
            json.dumps(asdict(tradecraft), indent=2), encoding="utf-8"
        )
    if governance is not None:
        payload = asdict(governance)
        if profile is not None:
            payload["profile"] = {
                "name": profile.name,
                "egress": profile.egress,
                "max_turns": profile.envelope.max_turns,
                "max_thinking_tokens": profile.envelope.max_thinking_tokens,
            }
        (out_dir / "governance.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
