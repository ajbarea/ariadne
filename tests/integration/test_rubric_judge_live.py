"""Gated integration test for the real Claude-backed analytic judge.

Skipped unless the optional ``rubric`` extra is installed (``uv sync --extra
rubric``) and ANTHROPIC_API_KEY is set — it makes real Claude Messages calls.
Mirrors the key-gated live-agent e2e pattern; the hermetic suite uses a fake judge.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("anthropic")

from ariadne.evaluation.judge import ClaudeAnalyticJudge
from ariadne.evaluation.rubric import ICD203_RUBRIC, score_note

pytestmark = pytest.mark.integration

# A note that argues from cited evidence, weighs an alternative, and states a
# 'so what' — should score well; a bare unsupported assertion should score low.
_STRONG_NOTE = (
    "# Workup: Halberd\n\n"
    "Halberd is a member of Signals-Cell [cite:g1], which is co-located with "
    "Logistics-Cell at Compound-Alpha [cite:g2]. This co-location is the basis for "
    "assessing a working relationship between the two cells. An alternative reading "
    "— that the shared site is incidental — is weakened by the repeated co-location "
    "across [cite:g2] and [cite:g3]. Implication: an analyst tracking Logistics-Cell "
    "should treat Halberd as a likely conduit.\n"
)
_WEAK_NOTE = "# Workup: Halberd\n\nHalberd runs everything. He is the most important person.\n"


@pytest.fixture(scope="module")
def judge() -> ClaudeAnalyticJudge:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("no ANTHROPIC_API_KEY — live judge run skipped")
    return ClaudeAnalyticJudge()


def test_judge_scores_every_dimension_in_range(judge: ClaudeAnalyticJudge) -> None:
    report = score_note(_STRONG_NOTE, judge)
    assert {s.key for s in report.dimensions} == {d.key for d in ICD203_RUBRIC}
    for s in report.dimensions:
        assert 1 <= s.score <= 5
        assert s.rationale.strip()
    assert 1.0 <= report.overall <= 5.0


def test_judge_ranks_a_reasoned_note_above_a_bare_assertion(judge: ClaudeAnalyticJudge) -> None:
    strong = score_note(_STRONG_NOTE, judge)
    weak = score_note(_WEAK_NOTE, judge)
    assert strong.overall > weak.overall
