"""Hermetic tests for the cross-store reconciliation eval score.

Reconciliation is a brief success criterion ("reconciling across modalities").
A note *reconciles* a cross-store fact when it (1) surfaces the fact, (2) uses
explicit reconciliation language — corroboration or conflict — and (3) actually
engaged both stores (the relational store appears in the ledger, not just the
graph). Merely mentioning two facts is not reconciliation.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from ariadne.evaluation.reconcile import (
    RECON_FIXTURES,
    SYNTHETIC_RECON,
    ReconciliationCase,
    ReconciliationFixture,
    score_reconciliation,
    score_reconciliation_dir,
)

if TYPE_CHECKING:
    from pathlib import Path

# A note that corroborates the Halberd↔Wren co-location across stores AND flags
# Talon's cross-store location conflict.
_GOOD_NOTE = """
## Relationships
Halberd and Wren are both at Compound-Alpha [cite:g1]; the personnel records
independently corroborate this co-location, consistent across both stores [cite:g2].

## Gaps & caveats
Talon's location conflicts across sources: the graph places his Signals-Cell at
Compound-Alpha, but the personnel record lists Compound-Beta [cite:g3] — flagged
as a discrepancy rather than silently resolved.
"""

# Same facts, but no reconciliation language — just two statements side by side.
_NO_CUE_NOTE = """
## Relationships
Halberd and Wren are at Compound-Alpha [cite:g1]. The personnel record shows
Wren at Compound-Alpha [cite:g2].

## Gaps & caveats
Talon is at Compound-Beta per the personnel record [cite:g3].
"""

# Ledger touching BOTH stores (graph CO_LOCATED + relational personnel).
_BOTH_STORES_LEDGER = [
    {"id": "g1", "tool_input": {"query": "MATCH (u)-[:CO_LOCATED]->(s) RETURN s"}},
    {"id": "g2", "tool_input": {"sql": "SELECT * FROM personnel"}},
    {"id": "g3", "tool_input": {"sql": "SELECT last_seen_site FROM personnel WHERE name='Talon'"}},
]

# Graph-only ledger — the relational store was never queried.
_GRAPH_ONLY_LEDGER = [
    {"id": "g1", "tool_input": {"query": "MATCH (u)-[:CO_LOCATED]->(s) RETURN s"}},
]


def test_synthetic_fixture_has_both_corroboration_and_conflict() -> None:
    assert SYNTHETIC_RECON.corroborations
    assert SYNTHETIC_RECON.conflicts
    assert RECON_FIXTURES["synthetic"] is SYNTHETIC_RECON


def test_good_note_with_both_stores_scores_perfect() -> None:
    report = score_reconciliation(_GOOD_NOTE, _BOTH_STORES_LEDGER, SYNTHETIC_RECON)
    assert report.corroboration == pytest.approx(1.0)
    assert report.conflict == pytest.approx(1.0)
    assert report.reconciliation == pytest.approx(1.0)
    assert report.handled == report.total


def test_facts_without_reconciliation_language_score_zero() -> None:
    # Mentioning both facts is not reconciling — no corroboration/conflict cue.
    report = score_reconciliation(_NO_CUE_NOTE, _BOTH_STORES_LEDGER, SYNTHETIC_RECON)
    assert report.corroboration == pytest.approx(0.0)
    assert report.conflict == pytest.approx(0.0)


def test_reconciliation_requires_both_stores_engaged() -> None:
    # Right language, but the relational store was never queried → not credited.
    report = score_reconciliation(_GOOD_NOTE, _GRAPH_ONLY_LEDGER, SYNTHETIC_RECON)
    assert report.reconciliation == pytest.approx(0.0)


def test_corroboration_and_conflict_scored_independently() -> None:
    fixture = ReconciliationFixture(
        entity="X",
        corroborations=(
            ReconciliationCase(
                fact_markers=("alpha",), cue_markers=("corroborat",), store_markers=("personnel",)
            ),
        ),
        conflicts=(
            ReconciliationCase(
                fact_markers=("beta",), cue_markers=("conflict",), store_markers=("personnel",)
            ),
        ),
    )
    note = "Alpha is corroborated by personnel."  # corroboration only; no conflict flagged
    report = score_reconciliation(note, [{"id": "g1", "tool_input": {"sql": "personnel"}}], fixture)
    assert report.corroboration == pytest.approx(1.0)
    assert report.conflict == pytest.approx(0.0)
    assert report.reconciliation == pytest.approx(0.5)


def test_score_reconciliation_dir_reads_artifacts(tmp_path: Path) -> None:
    (tmp_path / "note.md").write_text(_GOOD_NOTE, encoding="utf-8")
    (tmp_path / "provenance.jsonl").write_text(
        "\n".join(json.dumps(e) for e in _BOTH_STORES_LEDGER), encoding="utf-8"
    )
    report = score_reconciliation_dir(tmp_path, SYNTHETIC_RECON)
    assert report.reconciliation == pytest.approx(1.0)
