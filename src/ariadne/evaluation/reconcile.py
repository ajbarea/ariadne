"""Cross-store reconciliation scoring — a first-class eval criterion.

The brief lists "reconciling across modalities" as a success criterion. The
harness already reconciles in the loop (corroborate cross-store agreements,
flag conflicts); this scores whether a finished note actually did it.

A cross-store fact is *reconciled* when the note (1) **surfaces** the fact,
(2) uses explicit **reconciliation language** — corroboration when stores agree,
a conflict flag when they disagree — and (3) the workup actually **engaged both
stores** (the relational store appears in the ledger, not only the graph).
Mentioning two facts side by side is not reconciliation; the cue + the
both-stores requirement are what separate analysis from recitation.

# research(2026-06): grounds the brief's cross-modality reconciliation criterion;
# scored the same hermetic, marker-based way as the planted-needle harness
# (needle.py). See docs/research/analytic-rigor-eval.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ariadne.evaluation._text import all_present, any_present, statement_text

# Default cue vocabularies. Corroboration = stores independently agree; conflict
# = stores disagree and the note must say so rather than silently pick one.
_CORROBORATION_CUES = (
    "corroborat",
    "consistent",
    "independent",
    "both stores",
    "across both",
    "agree",
    "reinforc",
)
_CONFLICT_CUES = (
    "conflict",
    "disagree",
    "discrepan",
    "inconsist",
    "contradict",
    "mismatch",
)


@dataclass(frozen=True)
class ReconciliationCase:
    """One cross-store fact and the markers proving the note reconciled it.

    - ``fact_markers`` — all must appear in the note (the fact is surfaced).
    - ``cue_markers`` — at least one must appear in the note (reconciliation
      language: corroboration for agreements, a conflict flag for disagreements).
    - ``store_markers`` — all must appear in the ledger statements (proof both
      stores were engaged; the relational store does not appear unless queried).
    """

    fact_markers: tuple[str, ...]
    cue_markers: tuple[str, ...]
    store_markers: tuple[str, ...]


@dataclass(frozen=True)
class ReconciliationFixture:
    """Planted cross-store agreements and conflicts for one dataset."""

    entity: str
    corroborations: tuple[ReconciliationCase, ...]
    conflicts: tuple[ReconciliationCase, ...]


@dataclass(frozen=True)
class ReconciliationReport:
    """How well a note reconciled the fixture's cross-store cases."""

    entity: str
    corroboration: float  # fraction of corroboration cases properly handled
    conflict: float  # fraction of conflict cases properly flagged
    reconciliation: float  # all handled cases / all cases
    handled: int
    total: int


# The synthetic seed plants both phenomena (infra/neo4j/seed.cypher +
# infra/postgres/seed.sql):
#  - Corroboration: Halberd & Wren at Compound-Alpha is attested by the graph's
#    CO_LOCATED path AND the relational last_seen_site — agreement across stores.
#  - Conflict: Talon's location disagrees — the graph implies Compound-Alpha (his
#    Signals-Cell is co-located there), the personnel record says Compound-Beta.
SYNTHETIC_RECON = ReconciliationFixture(
    entity="Halberd",
    corroborations=(
        ReconciliationCase(
            fact_markers=("Wren", "Compound-Alpha"),
            cue_markers=_CORROBORATION_CUES,
            store_markers=("personnel",),
        ),
    ),
    conflicts=(
        ReconciliationCase(
            # Compound-Beta is relational-only, so requiring it proves the note
            # pulled the conflicting relational fact, not just the graph's site.
            fact_markers=("Talon", "Compound-Beta"),
            cue_markers=_CONFLICT_CUES,
            store_markers=("personnel",),
        ),
    ),
)

RECON_FIXTURES = {"synthetic": SYNTHETIC_RECON}


def _is_handled(case: ReconciliationCase, note_lower: str, ledger_lower: str) -> bool:
    return (
        all_present(case.fact_markers, note_lower)
        and any_present(case.cue_markers, note_lower)
        and all_present(case.store_markers, ledger_lower)
    )


def _group_score(cases: tuple[ReconciliationCase, ...], note_lower: str, ledger_lower: str) -> int:
    return sum(1 for c in cases if _is_handled(c, note_lower, ledger_lower))


def score_reconciliation(
    note: str, ledger_entries: list[dict], fixture: ReconciliationFixture
) -> ReconciliationReport:
    """Score how well ``note`` reconciled ``fixture``'s cross-store cases."""
    note_lower = note.lower()
    ledger_lower = "\n".join(statement_text(e) for e in ledger_entries).lower()
    corr_ok = _group_score(fixture.corroborations, note_lower, ledger_lower)
    conf_ok = _group_score(fixture.conflicts, note_lower, ledger_lower)
    n_corr = len(fixture.corroborations)
    n_conf = len(fixture.conflicts)
    total = n_corr + n_conf
    handled = corr_ok + conf_ok
    return ReconciliationReport(
        entity=fixture.entity,
        corroboration=corr_ok / n_corr if n_corr else 1.0,
        conflict=conf_ok / n_conf if n_conf else 1.0,
        reconciliation=handled / total if total else 1.0,
        handled=handled,
        total=total,
    )


def score_reconciliation_dir(
    out_dir: str | Path, fixture: ReconciliationFixture
) -> ReconciliationReport:
    """Read ``note.md`` + ``provenance.jsonl`` from a workup dir and score them."""
    out_dir = Path(out_dir)
    note = (out_dir / "note.md").read_text(encoding="utf-8")
    lines = (out_dir / "provenance.jsonl").read_text(encoding="utf-8").splitlines()
    entries = [json.loads(line) for line in lines if line.strip()]
    return score_reconciliation(note, entries, fixture)
