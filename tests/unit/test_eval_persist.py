"""Persisting eval + rubric scores to JSON so the HTML report can surface them."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ariadne.evaluation.needle import HALBERD_FIXTURE, score_workup, write_eval_json
from ariadne.evaluation.rubric import DimensionScore, RubricReport, write_rubric_json

if TYPE_CHECKING:
    from pathlib import Path


def test_write_eval_json_persists_the_scored_dimensions(tmp_path: Path) -> None:
    note = "Compound-Alpha, co-located [cite:g1]."
    entries = [
        {"id": "g1", "tool_input": {"query": "MEMBER_OF CO_LOCATED"}},
        {"id": "g2", "tool_input": {"query": "x"}},
    ]
    report = score_workup(note, entries, HALBERD_FIXTURE)
    path = write_eval_json(tmp_path, report, "halberd")
    assert path == tmp_path / "eval.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["fixture"] == "halberd"
    assert data["grounded"] is True
    assert data["recall"] == 1.0
    assert "supporting_fact_f1" in data
    assert "context_utilization" in data


def test_write_rubric_json_persists_overall_and_dimensions(tmp_path: Path) -> None:
    report = RubricReport(
        dimensions=(
            DimensionScore(key="alternatives", score=5, rationale="ACH present."),
            DimensionScore(key="argumentation", score=4, rationale="Mostly sound."),
        ),
        overall=4.5,
    )
    path = write_rubric_json(tmp_path, report)
    assert path == tmp_path / "rubric.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["overall"] == 4.5
    assert data["dimensions"][0] == {
        "key": "alternatives",
        "score": 5,
        "rationale": "ACH present.",
    }
