"""Persist a workup run's artifacts to an output directory."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ariadne.profiles import Profile  # noqa: TC001
from ariadne.provenance.citations import CitationReport, CoverageStats  # noqa: TC001
from ariadne.provenance.governance import GovernanceReport  # noqa: TC001
from ariadne.provenance.ledger import ProvenanceLedger  # noqa: TC001
from ariadne.provenance.tradecraft import TradecraftReport  # noqa: TC001


def _coverage_payload(
    before: CoverageStats | None, after: CoverageStats, passes: int | None
) -> dict[str, float | int | None]:
    """Build the citations.json ``coverage`` block: raw->repaired fraction, Δ gain, counts.

    ``gain`` is ``after - before`` when a repair baseline exists and both fractions
    are defined, else ``None`` — so ``--no-repair`` (no baseline) reports ``null``,
    distinct from a real ``0.0`` gain (repair ran and found nothing to fix). ADR-0023.
    """
    before_f = before.fraction if before is not None else None
    gain = (
        after.fraction - before_f if before_f is not None and after.fraction is not None else None
    )
    return {
        "before": before_f,
        "after": after.fraction,
        "gain": gain,
        "covered": after.covered,
        "total": after.total,
        "passes": passes,
    }


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
    coverage_before: CoverageStats | None = None,
    coverage_after: CoverageStats | None = None,
    repair_passes: int | None = None,
) -> None:
    """Write ``note.md``, ``provenance.jsonl``, ``citations.json`` (and, when supplied,
    the advisory ``tradecraft.json`` / ``governance.json``) to ``out_dir``.

    When ``coverage_after`` is given, ``citations.json`` also carries a ``coverage``
    block (raw->repaired fraction + Δ gain + counts) — the repair loop's measured
    coverage gain (ADR-0023)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "note.md").write_text(note, encoding="utf-8")
    ledger.write_jsonl(out_dir / "provenance.jsonl")
    payload = {"entity": entity, **asdict(report)}
    if coverage_after is not None:
        payload["coverage"] = _coverage_payload(coverage_before, coverage_after, repair_passes)
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
