"""Deepen an existing skill from a new certified run — `distil --into` (ADR-0032).

Trace-conditioned revision: existing skill + a new certified trajectory -> a bounded, revised
skill (LLM-only; integrating the generalizable lesson, not this run's specifics). Proposed for
ratification, validated by `ariadne compare`.
"""

from __future__ import annotations

import pytest

from ariadne.learning.distil import (
    NotCertified,
    build_deepen_prompt,
    distil_deepen,
    parse_skill_md,
)
from ariadne.learning.runs import RunArtifacts

_TRAJECTORY = [
    {
        "id": "g1",
        "tool": "mcp__neo4j__read_neo4j_cypher",
        "tool_input": {"query": "MATCH (p:Person {name:'Halberd'})-[:MEMBER_OF]->(u) RETURN u"},
    },
    {
        "id": "g2",
        "tool": "mcp__postgres__execute_sql",
        "tool_input": {"sql": "SELECT * FROM personnel WHERE alias = 'H1'"},
    },
]

_EVAL = {"entity": "Halberd", "grounded": True, "recall": 1.0, "fixture": "halberd"}
_MANIFEST = {"run_id": "R1", "dataset": "synthetic", "entity": "Halberd", "git_sha": "abc"}

_EXISTING_SKILL = (
    "---\n"
    "name: entity-workup\n"
    'description: "Work up an entity and produce a cited note."\n'
    "---\n\n"
    "# Entity Workup\n\n"
    "## Loop\nGather, act, verify, synthesize. SENTINEL-EXISTING-BODY.\n"
)


def _run(*, eval_scores: dict | None = None) -> RunArtifacts:
    return RunArtifacts(
        run_dir="runs/synthetic/halberd/R1",
        provenance=_TRAJECTORY,
        eval_scores=_EVAL if eval_scores is None else eval_scores,
        manifest=_MANIFEST,
        note="# Note\nHalberd leads Signals-Cell [cite:g1].",
    )


def test_parse_skill_md_extracts_name_description_body() -> None:
    name, desc, body = parse_skill_md(_EXISTING_SKILL)
    assert name == "entity-workup"
    assert "cited note" in desc
    assert "SENTINEL-EXISTING-BODY" in body


def test_deepen_gates_on_certification() -> None:
    ungrounded = {**_EVAL, "grounded": False}
    with pytest.raises(NotCertified):
        distil_deepen(
            _run(eval_scores=ungrounded), existing_skill_md=_EXISTING_SKILL, call_llm=lambda _p: {}
        )


def test_deepen_prompt_grounds_in_existing_skill_and_new_run() -> None:
    prompt = build_deepen_prompt(_run(), "entity-workup", "SENTINEL-EXISTING-BODY", ("graph",))
    # the existing skill body AND the new run's evidence are both in the prompt
    assert "SENTINEL-EXISTING-BODY" in prompt
    assert "MEMBER_OF" in prompt
    # the anti-overfitting / bounded-integration instruction is present
    assert "bounded" in prompt.lower()
    assert "hard-code" in prompt.lower() or "generaliz" in prompt.lower()


def test_deepen_integrates_via_the_injected_call() -> None:
    proposed = {
        "name": "ignored-by-deepen",
        "description": "Work up an entity across stores with a closing citation audit.",
        "body": "# Entity Workup\n\n## Loop\n...REVISED with a closing audit step.\n",
    }
    seen: dict[str, str] = {}

    def fake_call(prompt: str) -> dict:
        seen["prompt"] = prompt
        return proposed

    skill = distil_deepen(
        _run(), existing_skill_md=_EXISTING_SKILL, call_llm=fake_call, model="claude-opus-4-8"
    )
    # deepen keeps the existing skill's identity (name), not the model's proposed name
    assert skill.card.name == "entity-workup"
    assert skill.card.description == proposed["description"]
    assert "REVISED with a closing audit step" in skill.skill_md
    # marked as a deepen revision, with this run as the source + reliability
    assert skill.card.distilled_by == "llm:claude-opus-4-8:deepen"
    assert skill.card.reliability["grounded"] is True
    assert skill.card.source["run_id"] == "R1"
    # the prompt carried both the existing body and the new trajectory
    assert "SENTINEL-EXISTING-BODY" in seen["prompt"]
    assert "MEMBER_OF" in seen["prompt"]


def test_deepen_name_override_wins() -> None:
    proposed = {"description": "d", "body": "b"}
    skill = distil_deepen(
        _run(), existing_skill_md=_EXISTING_SKILL, call_llm=lambda _p: proposed, name="my-name"
    )
    assert skill.card.name == "my-name"


def test_deepen_rejects_an_incomplete_proposal() -> None:
    # truncation guard (the B2 lesson): a missing body is a clear error, not a KeyError.
    with pytest.raises(RuntimeError, match="body"):
        distil_deepen(
            _run(), existing_skill_md=_EXISTING_SKILL, call_llm=lambda _p: {"description": "d"}
        )
