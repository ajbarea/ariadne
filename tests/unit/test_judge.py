"""Hermetic tests for the real Claude judge's pure helpers.

The model call itself is a gated integration test (needs ANTHROPIC_API_KEY + the
``rubric`` extra); here we test only the pure prompt builder and the tool-result
parser, which need no network.
"""

from __future__ import annotations

import pytest

from ariadne.evaluation.judge import SCORE_TOOL, build_rubric_prompt, parse_score
from ariadne.evaluation.rubric import ICD203_RUBRIC

_DIM = ICD203_RUBRIC[0]


def test_prompt_embeds_the_standard_question_and_every_anchor() -> None:
    prompt = build_rubric_prompt("the analytic note text", _DIM)
    assert _DIM.standard in prompt
    assert _DIM.question in prompt
    for level, descriptor in _DIM.anchors.items():
        assert str(level) in prompt
        assert descriptor in prompt
    assert "the analytic note text" in prompt


def test_prompt_carries_length_neutrality_to_curb_verbosity_bias() -> None:
    # Web-searched June-2026 best practice: LLM judges over-reward length; the
    # prompt must tell the judge to score quality, not length.
    prompt = build_rubric_prompt("note", _DIM).lower()
    assert "length" in prompt


def test_score_tool_constrains_score_to_the_one_to_five_scale() -> None:
    schema = SCORE_TOOL["input_schema"]
    score = schema["properties"]["score"]
    assert score["type"] == "integer"
    assert score["minimum"] == 1
    assert score["maximum"] == 5
    # Reason-before-score: the rationale is a required field, not optional padding.
    assert set(schema["required"]) == {"score", "rationale"}


def test_parse_score_reads_a_forced_tool_use_block() -> None:
    score = parse_score(
        "argumentation",
        {"score": 4, "rationale": "evidence-linked, one minor gap"},
    )
    assert score.key == "argumentation"
    assert score.score == 4
    assert score.rationale == "evidence-linked, one minor gap"


def test_parse_score_clamps_out_of_range_scores() -> None:
    # A model that ignores the schema bound must not produce an out-of-scale score
    # that would corrupt the mean.
    assert parse_score("k", {"score": 9, "rationale": "x"}).score == 5
    assert parse_score("k", {"score": 0, "rationale": "x"}).score == 1


def test_parse_score_rejects_a_non_integer_score() -> None:
    with pytest.raises((TypeError, ValueError)):
        parse_score("k", {"score": "high", "rationale": "x"})
