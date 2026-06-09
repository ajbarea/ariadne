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


# --- self-consistency sampling (ADR-0035) ---------------------------------------------
#
# A single LLM judgment is noisy (position/verbosity/self-preference bias). `samples > 1`
# re-judges each dimension N times and aggregates by MEDIAN (robust to an outlier judgment),
# reporting the inter-sample stdev as `spread` so the analyst sees where the judge is unstable.


class SequenceJudge:
    """``AnalyticJudge`` returning a preset *sequence* of scores per dimension across calls,
    so a test can simulate judge sampling variance (the same dimension scored differently)."""

    def __init__(self, sequences: dict[str, list[int]]) -> None:
        self._seqs = sequences
        self._calls: dict[str, int] = {}
        self.seen: list[tuple[str, str]] = []

    def score(self, note: str, dimension: RubricDimension) -> DimensionScore:
        i = self._calls.get(dimension.key, 0)
        self._calls[dimension.key] = i + 1
        value = self._seqs[dimension.key][i % len(self._seqs[dimension.key])]
        self.seen.append((dimension.key, note))
        return DimensionScore(key=dimension.key, score=value, rationale=f"r{value}")


def test_samples_one_is_unchanged_single_judgment() -> None:
    judge = _judge_giving(4)
    report = score_note("note", judge, samples=1)
    assert len(judge.seen) == len(ICD203_RUBRIC)  # one judgment per dimension, as before
    assert report.overall == pytest.approx(4.0)
    assert all(d.spread == 0.0 for d in report.dimensions)  # no disagreement to report
    assert report.overall_spread == 0.0


def test_samples_n_rejudges_each_dimension_n_times() -> None:
    judge = SequenceJudge({d.key: [3, 4, 5] for d in ICD203_RUBRIC})
    score_note("note", judge, samples=3)
    per_key = {k: sum(1 for kk, _ in judge.seen if kk == k) for k, _ in judge.seen}
    assert all(count == 3 for count in per_key.values())
    assert len(judge.seen) == 3 * len(ICD203_RUBRIC)


def test_samples_aggregate_by_median_robust_to_outlier() -> None:
    # 1 is an outlier judgment; the median (4) ignores it where a mean (3.33) would be dragged down.
    judge = SequenceJudge({d.key: [1, 5, 4] for d in ICD203_RUBRIC})
    report = score_note("note", judge, samples=3)
    assert all(d.score == 4 for d in report.dimensions)
    assert report.overall == pytest.approx(4.0)


def test_spread_is_stdev_of_the_samples() -> None:
    import statistics

    judge = SequenceJudge({d.key: [1, 5, 4] for d in ICD203_RUBRIC})
    report = score_note("note", judge, samples=3)
    expected = statistics.pstdev([1, 5, 4])
    assert all(d.spread == pytest.approx(expected) for d in report.dimensions)
    assert report.overall_spread == pytest.approx(expected)


def test_unanimous_samples_report_zero_spread() -> None:
    judge = SequenceJudge({d.key: [4, 4, 4] for d in ICD203_RUBRIC})
    report = score_note("note", judge, samples=3)
    assert all(d.spread == 0.0 for d in report.dimensions)
    assert report.overall_spread == 0.0


def test_representative_rationale_comes_from_a_sample_at_the_median() -> None:
    judge = SequenceJudge({d.key: [1, 5, 4] for d in ICD203_RUBRIC})  # median 4 -> rationale "r4"
    report = score_note("note", judge, samples=3)
    assert all(d.rationale == "r4" for d in report.dimensions)


def test_samples_below_one_is_rejected() -> None:
    with pytest.raises(ValueError, match="samples"):
        score_note("note", _judge_giving(3), samples=0)
