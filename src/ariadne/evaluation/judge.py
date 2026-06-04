"""Claude-backed ``AnalyticJudge`` for the LLM-rubric (real model path).

Scores one rubric dimension per call with a single Claude Messages request that
*forces* a ``submit_score`` tool call, so the result is structured (an integer
1-5 + a rationale) rather than free text to parse. The ``anthropic`` client is
the optional ``rubric`` extra, imported lazily so the static checker and the
core package stay clean without it — the same pattern as ``provenance.entailment``.

# research(2026-06): structured tool-use output + criterion-by-criterion scoring
# + an anchored 1-5 scale are the current LLM-as-judge best practice. Two named
# judge biases are mitigated here: verbosity (the prompt scores quality, not
# length) and format/anchoring (rationale-before-score, a forced schema). See
# docs/research/analytic-rigor-eval.md and ADR-0011.
"""

from __future__ import annotations

from typing import Any

from ariadne.evaluation.rubric import DimensionScore, RubricDimension

_DEFAULT_MODEL = "claude-opus-4-8"

# Forced-tool schema: the judge must return a 1-5 integer and a rationale. The
# scale bound lives in the schema so a compliant model never scores off-scale.
SCORE_TOOL: dict[str, Any] = {
    "name": "submit_score",
    "description": "Submit the rubric score for the single dimension under review.",
    "input_schema": {
        "type": "object",
        "properties": {
            "rationale": {
                "type": "string",
                "description": "One or two sentences justifying the score against the anchors. "
                "Decide this before the score.",
            },
            "score": {
                "type": "integer",
                "minimum": 1,
                "maximum": 5,
                "description": "The anchored level (1-5) the note reaches on this dimension.",
            },
        },
        "required": ["score", "rationale"],
    },
}

_SYSTEM = (
    "You are a rigorous intelligence-analysis reviewer applying ICD-203 tradecraft "
    "standards. Score the note on ONE dimension only, using the anchored levels. "
    "Judge analytic quality, not length: a concise note that fully satisfies the "
    "criterion scores as high as a long one. Decide your rationale first, then the "
    "score, and submit both with the submit_score tool."
)


def build_rubric_prompt(note: str, dimension: RubricDimension) -> str:
    """Build the user prompt scoring ``note`` against a single ``dimension``."""
    anchors = "\n".join(f"  {level}: {text}" for level, text in sorted(dimension.anchors.items()))
    return (
        f"Standard: {dimension.standard}\n"
        f"Criterion: {dimension.question}\n\n"
        f"Anchored levels (1 lowest, 5 highest):\n{anchors}\n\n"
        f"Analytic note under review:\n---\n{note}\n---\n\n"
        "Score this one dimension on quality, not length."
    )


def parse_score(key: str, tool_input: dict[str, Any]) -> DimensionScore:
    """Turn a ``submit_score`` tool input into a ``DimensionScore``.

    The schema bounds the score 1-5, but a model can still ignore it, so clamp to
    the scale rather than let an out-of-range value corrupt the aggregate mean. A
    non-integer score is a contract violation and raises.
    """
    raw = tool_input["score"]
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise TypeError(f"score must be an integer, got {raw!r}")
    score = max(1, min(5, raw))
    return DimensionScore(key=key, score=score, rationale=str(tool_input.get("rationale", "")))


class ClaudeAnalyticJudge:
    """An ``AnalyticJudge`` backed by the Claude Messages API. Requires the ``rubric`` extra."""

    def __init__(self, *, model: str = _DEFAULT_MODEL, max_tokens: int = 512) -> None:
        # Dynamic import: `anthropic` is the optional `rubric` extra, so the static
        # checker must not try to resolve it whether or not it is installed.
        import importlib

        anthropic = importlib.import_module("anthropic")
        # `Any`: the client is from the optional `rubric` extra, so its precise
        # types only exist when installed. Typing it loosely keeps `make lint`
        # stable whether or not the extra is synced (the optional-extra trap).
        self._client: Any = anthropic.Anthropic()
        self._model = model
        self._max_tokens = max_tokens

    def score(self, note: str, dimension: RubricDimension) -> DimensionScore:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=_SYSTEM,
            tools=[SCORE_TOOL],
            tool_choice={"type": "tool", "name": "submit_score"},
            messages=[{"role": "user", "content": build_rubric_prompt(note, dimension)}],
        )
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == "submit_score":
                return parse_score(dimension.key, dict(block.input))
        raise RuntimeError("judge did not return a submit_score tool call")
