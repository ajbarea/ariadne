"""LLM-rubric scoring of an analytic note against ICD-203 tradecraft standards.

The mechanical gates already cover the *checkable* standards — sourcing (the
citation gate), expression of uncertainty (the WEP tradecraft lint), and the
fact-vs-judgment split (``tradecraft.is_analytic_judgment``). What they cannot
score is analytic *quality*: did the note weigh alternatives, argue logically
from its evidence, stay relevant to the question, and keep its judgments
proportionate to what the evidence supports? Those need a reader's judgment.

This module supplies the deployable subset of **LLM-Rubric** (Hashemi & Eisner,
ACL 2024, arXiv:2501.00274): a manually authored, criterion-separated rubric, an
LLM scoring each dimension pointwise on an anchored 1-5 scale, aggregated to an
overall. The judge is an injected ``AnalyticJudge`` Protocol, so the engine is
pure and hermetic — the real model lives in ``evaluation.judge`` behind the
``rubric`` extra.

# research(2026-06): pointwise analytic rubrics are the right tool for
# "debugging and longitudinal monitoring" (vs pairwise for model selection);
# best practice is criterion-by-criterion scoring with structured output, a
# narrow anchored scale (1-5), and per-level calibration descriptors. The
# anchors below ARE those descriptors. See docs/research/analytic-rigor-eval.md
# and ADR-0011.
#
# LIMIT: LLM-Rubric's full method trains a small calibration network on human
# annotations to predict an overall human score. Ariadne has no human-annotated
# set yet, so this is the rubric-scoring subset (mean of dimensions); the
# calibration network is the documented extension for when annotations exist.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class RubricDimension:
    """One ICD-203 standard, framed as a scored criterion with anchored levels."""

    key: str
    standard: str  # the ICD-203 standard this dimension scores
    question: str  # the criterion the judge answers
    anchors: dict[int, str]  # 1..5 -> what a note at that level looks like


@dataclass(frozen=True)
class DimensionScore:
    """A judge's score (1-5) for one dimension, with its reasoning."""

    key: str
    score: int
    rationale: str


@dataclass(frozen=True)
class RubricReport:
    """All dimension scores for a note plus the aggregate (mean, 1-5)."""

    dimensions: tuple[DimensionScore, ...]
    overall: float


class AnalyticJudge(Protocol):
    """Scores ``note`` against one ``dimension``. Implemented by ClaudeAnalyticJudge."""

    def score(self, note: str, dimension: RubricDimension) -> DimensionScore: ...


# The ICD-203 standards a reader must judge — deliberately the ones the mechanical
# gates do NOT cover, so the rubric complements rather than re-checks them.
ICD203_RUBRIC: tuple[RubricDimension, ...] = (
    RubricDimension(
        key="alternatives",
        standard="ICD-203 #4 — analysis of alternatives",
        question=(
            "Does the note consider alternative explanations for the evidence and "
            "say why the lead judgment is preferred, rather than asserting a single "
            "story?"
        ),
        anchors={
            1: "No alternative is acknowledged; a single explanation is asserted.",
            2: "Gestures at uncertainty but names no concrete alternative.",
            3: "Names an alternative but does not weigh it against the evidence.",
            4: "Weighs at least one alternative against the evidence.",
            5: "Enumerates competing hypotheses and marshals cited evidence for/against each.",
        },
    ),
    RubricDimension(
        key="argumentation",
        standard="ICD-203 #6 — clear and logical argumentation",
        question=(
            "Does each judgment follow logically from the cited evidence, with the "
            "reasoning visible and internally consistent (no leaps, no contradictions)?"
        ),
        anchors={
            1: "Conclusions do not follow from the evidence, or contradict each other.",
            2: "Reasoning is mostly asserted; the link from evidence to judgment is opaque.",
            3: "Reasoning is present but has a gap or an unjustified leap.",
            4: "Each judgment is traceable to its evidence with minor gaps.",
            5: "Every judgment is explicitly and consistently derived from cited evidence.",
        },
    ),
    RubricDimension(
        key="relevance",
        standard="ICD-203 #5 — customer relevance and implications",
        question=(
            "Does the note answer the analytic question about the target entity and "
            "address the implications (the 'so what'), not just recite facts?"
        ),
        anchors={
            1: "Recites facts with no bearing on the analytic question.",
            2: "On topic but never states an implication or 'so what'.",
            3: "Answers the question but leaves implications implicit.",
            4: "Answers the question and states implications.",
            5: "Directly answers and draws out implications that change the analyst's picture.",
        },
    ),
    RubricDimension(
        key="accuracy",
        standard="ICD-203 #8 — accuracy of judgments",
        question=(
            "Are the judgments proportionate to the cited evidence — neither "
            "overreaching beyond what it supports nor underselling what it shows?"
        ),
        anchors={
            1: "Judgments overreach or contradict the cited evidence.",
            2: "Several judgments claim more (or less) than the evidence supports.",
            3: "Generally proportionate, with one notable over- or under-reach.",
            4: "Judgments are proportionate to the evidence with minor calibration slips.",
            5: "Every judgment is calibrated to exactly what the cited evidence supports.",
        },
    ),
)


def score_note(
    note: str,
    judge: AnalyticJudge,
    rubric: tuple[RubricDimension, ...] = ICD203_RUBRIC,
) -> RubricReport:
    """Score ``note`` against every rubric dimension and aggregate (mean of 1-5)."""
    scores = tuple(judge.score(note, dimension) for dimension in rubric)
    overall = sum(s.score for s in scores) / len(scores) if scores else 0.0
    return RubricReport(dimensions=scores, overall=overall)


def score_note_dir(
    out_dir: str | Path,
    judge: AnalyticJudge,
    rubric: tuple[RubricDimension, ...] = ICD203_RUBRIC,
) -> RubricReport:
    """Read ``note.md`` from a workup dir and score it."""
    note = (Path(out_dir) / "note.md").read_text(encoding="utf-8")
    return score_note(note, judge, rubric)


def write_rubric_json(out_dir: str | Path, report: RubricReport) -> Path:
    """Persist a rubric ``report`` to ``rubric.json`` so the HTML report can show it."""
    payload = {
        "overall": report.overall,
        "dimensions": [asdict(d) for d in report.dimensions],
    }
    path = Path(out_dir) / "rubric.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
