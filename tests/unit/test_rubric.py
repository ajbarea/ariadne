"""Hermetic tests for the LLM-rubric analytic-standards scoring engine.

The engine is pure: an injected ``AnalyticJudge`` scores each rubric dimension,
and ``score_note`` aggregates. The default path never touches a model — these
tests use a ``FakeJudge``, mirroring the FakeEmbedder / fake-EntailmentVerifier
DI pattern elsewhere in the package.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from ariadne.evaluation.rubric import (
    ICD203_RUBRIC,
    DimensionScore,
    RubricDimension,
    RubricReport,
    score_note,
    score_note_dir,
)

if TYPE_CHECKING:
    from pathlib import Path


class FakeJudge:
    """Deterministic ``AnalyticJudge``: returns a preset score per dimension key.

    Records every (dimension key, note) it was asked about so a test can assert
    the engine scored each dimension exactly once, criterion by criterion.
    """

    def __init__(self, scores: dict[str, int]) -> None:
        self._scores = scores
        self.seen: list[tuple[str, str]] = []

    def score(self, note: str, dimension: RubricDimension) -> DimensionScore:
        self.seen.append((dimension.key, note))
        return DimensionScore(
            key=dimension.key, score=self._scores[dimension.key], rationale="fake"
        )


def _judge_giving(value: int) -> FakeJudge:
    return FakeJudge({d.key: value for d in ICD203_RUBRIC})


def test_icd203_rubric_is_nonempty_and_well_formed() -> None:
    assert len(ICD203_RUBRIC) >= 3
    keys = [d.key for d in ICD203_RUBRIC]
    assert len(keys) == len(set(keys)), "dimension keys must be unique"
    for d in ICD203_RUBRIC:
        assert d.key and d.standard and d.question
        # Anchored 1-5 scale: every score level has a calibration descriptor.
        assert set(d.anchors) == {1, 2, 3, 4, 5}
        assert all(text.strip() for text in d.anchors.values())


def test_score_note_scores_every_dimension_once() -> None:
    judge = _judge_giving(4)
    report = score_note("a note", judge)
    assert isinstance(report, RubricReport)
    assert {s.key for s in report.dimensions} == {d.key for d in ICD203_RUBRIC}
    # Criterion-by-criterion: each dimension judged exactly once, on this note.
    assert sorted(k for k, _ in judge.seen) == sorted(d.key for d in ICD203_RUBRIC)
    assert all(note == "a note" for _, note in judge.seen)


def test_overall_is_mean_of_dimension_scores() -> None:
    first, *rest = ICD203_RUBRIC
    scores = {first.key: 5, **{d.key: 1 for d in rest}}
    report = score_note("note", FakeJudge(scores))
    expected = (5 + len(rest)) / len(ICD203_RUBRIC)
    assert report.overall == pytest.approx(expected)


def test_overall_with_uniform_scores_equals_that_score() -> None:
    report = score_note("note", _judge_giving(3))
    assert report.overall == pytest.approx(3.0)


def test_score_note_dir_reads_note_md(tmp_path: Path) -> None:
    (tmp_path / "note.md").write_text("# Analytic note\nHalberd is a member.", encoding="utf-8")
    judge = _judge_giving(5)
    report = score_note_dir(tmp_path, judge)
    assert report.overall == pytest.approx(5.0)
    # The judge saw the file's contents, not the path.
    assert all("Halberd is a member." in note for _, note in judge.seen)
