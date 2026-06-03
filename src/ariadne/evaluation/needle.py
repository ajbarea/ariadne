"""Planted-needle scoring against a known ground-truth fixture.

The seed graph plants one non-obvious multi-hop bridge (Halberd's Signals-Cell
shares Compound-Alpha with Logistics-Cell). That known answer lets us score a
workup against the brief's four success criteria without a human in the loop:

- **recall** — did the note *surface* the needle? (answer markers present)
- **trajectory** — did the provenance *actually traverse* it, or guess? (the
  required relationships appear in the ledger's queries)
- **grounded** — surfaced AND traversed: a note that names the bridge with no
  ledger query walking it is a guess and must fail this gate.
- **pivot_burden** — queries run per true hop (an efficiency proxy for the
  analyst-pivot burden the harness is meant to reduce).

# research(2026-06): planted-needle / supporting-fact eval (MuSiQue, HotpotQA
# supporting-fact F1) + trajectory grading (AgenticRAGTracer). Pure over the
# note text + ledger; supporting-fact F1 over individual edges is a later
# refinement. See docs/research/analytic-rigor-eval.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SupportingFact:
    """One gold edge of a needle, scored independently for per-edge F1.

    ``note_markers`` all present in the note ⇒ the edge is *surfaced*;
    ``ledger_markers`` all present in the ledger statements ⇒ it was *traversed*.
    An edge is *grounded* only when both hold — surfacing without traversing is a
    guess, the same gate the aggregate ``grounded`` applies at the whole-needle level.
    """

    note_markers: tuple[str, ...]
    ledger_markers: tuple[str, ...]


@dataclass(frozen=True)
class NeedleFixture:
    """Ground truth for one planted needle."""

    entity: str
    answer_markers: tuple[str, ...]  # substrings whose presence in the note = surfaced
    traversal_markers: tuple[str, ...]  # substrings that must appear in the ledger's queries
    min_hops: int  # the needle's true hop depth (pivot-burden denominator)
    supporting_facts: tuple[SupportingFact, ...] = ()  # gold edges for per-edge F1 (opt-in)


@dataclass(frozen=True)
class EvalReport:
    """Score of one workup against a needle fixture."""

    entity: str
    recall: float
    trajectory: float
    grounded: bool
    pivot_burden: float
    queries_run: int
    # Per-edge supporting-fact scores (HotpotQA/MuSiQue-style); None when the
    # fixture defines no supporting_facts.
    supporting_fact_precision: float | None = None
    supporting_fact_recall: float | None = None
    supporting_fact_f1: float | None = None


# The seed's planted length-3 bridge:
# Halberd -MEMBER_OF-> Signals-Cell -CO_LOCATED-> Compound-Alpha -CO_LOCATED-> Logistics-Cell
HALBERD_FIXTURE = NeedleFixture(
    entity="Halberd",
    answer_markers=("Compound-Alpha", "co-locat"),
    # Relationship types only — these prove the path was walked. The bridge node
    # name belongs in answer_markers (recall): an agent can traverse *to* it via
    # relationships without ever querying it by name.
    traversal_markers=("MEMBER_OF", "CO_LOCATED"),
    min_hops=3,
    supporting_facts=(
        SupportingFact(note_markers=("Signals",), ledger_markers=("MEMBER_OF",)),
        SupportingFact(note_markers=("Compound-Alpha",), ledger_markers=("CO_LOCATED",)),
        SupportingFact(note_markers=("Logistics",), ledger_markers=("CO_LOCATED",)),
    ),
)

# The seed's planted cross-modality tie (invisible in the graph):
# Halberd (H1) and Wren (W4) share cover_employer 'Meridian Freight Ltd' in the
# relational `personnel` table. Surfacing it requires actually querying the
# relational store — the graph cannot supply it.
WREN_TIE_FIXTURE = NeedleFixture(
    entity="Halberd",
    answer_markers=("Meridian Freight", "Wren"),
    # The relational table name proves the store was engaged for personnel data.
    # We deliberately do NOT require the `cover_employer` column in the statement:
    # a `SELECT *` surfaces the tie without naming the column, exactly as a graph
    # traversal reaches a node without naming it (see HALBERD_FIXTURE).
    traversal_markers=("personnel",),
    min_hops=2,
    supporting_facts=(
        SupportingFact(note_markers=("Meridian Freight",), ledger_markers=("personnel",)),
        SupportingFact(note_markers=("Wren",), ledger_markers=("personnel",)),
    ),
)

# CLI-selectable fixtures, keyed by a short slug (see `ariadne eval --fixture`).
FIXTURES = {"halberd": HALBERD_FIXTURE, "wren-tie": WREN_TIE_FIXTURE}


def _fraction_present(markers: tuple[str, ...], haystack_lower: str) -> float:
    if not markers:
        return 1.0
    found = sum(1 for m in markers if m.lower() in haystack_lower)
    return found / len(markers)


def _statement_text(entry: dict) -> str:
    """Join every string-valued tool arg so scoring is connector-agnostic.

    Cypher lands under ``query``, postgres-mcp under ``sql``; scanning all string
    args means a new connector's statement key needs no change here.
    """
    tool_input = entry.get("tool_input", {})
    if not isinstance(tool_input, dict):
        return ""
    return "\n".join(v for v in tool_input.values() if isinstance(v, str))


def _all_present(markers: tuple[str, ...], haystack_lower: str) -> bool:
    return all(m.lower() in haystack_lower for m in markers)


def _supporting_fact_scores(
    facts: tuple[SupportingFact, ...], note_lower: str, queries_lower: str
) -> tuple[float | None, float | None, float | None]:
    """Per-edge precision / recall / F1, or ``(None, None, None)`` if no facts.

    Each gold edge is *grounded* iff surfaced in the note AND traversed in the
    ledger. Recall = grounded / gold (did we properly ground the true edges);
    precision = grounded / surfaced (of the edges the note asserts, how many were
    actually walked — penalises fabricated edges). F1 is their harmonic mean.
    """
    if not facts:
        return None, None, None
    surfaced = [f for f in facts if _all_present(f.note_markers, note_lower)]
    grounded = [f for f in surfaced if _all_present(f.ledger_markers, queries_lower)]
    recall = len(grounded) / len(facts)
    precision = len(grounded) / len(surfaced) if surfaced else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def score_workup(note: str, ledger_entries: list[dict], fixture: NeedleFixture) -> EvalReport:
    """Score a workup's note + ledger entries against ``fixture``."""
    note_lower = note.lower()
    queries_lower = "\n".join(_statement_text(e) for e in ledger_entries).lower()
    recall = _fraction_present(fixture.answer_markers, note_lower)
    trajectory = _fraction_present(fixture.traversal_markers, queries_lower)
    queries_run = len(ledger_entries)
    pivot_burden = queries_run / fixture.min_hops if fixture.min_hops else float(queries_run)
    sf_precision, sf_recall, sf_f1 = _supporting_fact_scores(
        fixture.supporting_facts, note_lower, queries_lower
    )
    return EvalReport(
        entity=fixture.entity,
        recall=recall,
        trajectory=trajectory,
        grounded=recall == 1.0 and trajectory == 1.0,
        pivot_burden=pivot_burden,
        queries_run=queries_run,
        supporting_fact_precision=sf_precision,
        supporting_fact_recall=sf_recall,
        supporting_fact_f1=sf_f1,
    )


def score_workup_dir(out_dir: str | Path, fixture: NeedleFixture) -> EvalReport:
    """Read ``note.md`` + ``provenance.jsonl`` from ``out_dir`` and score them."""
    out_dir = Path(out_dir)
    note = (out_dir / "note.md").read_text(encoding="utf-8")
    lines = (out_dir / "provenance.jsonl").read_text(encoding="utf-8").splitlines()
    entries = [json.loads(line) for line in lines if line.strip()]
    return score_workup(note, entries, fixture)
