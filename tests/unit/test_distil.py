"""Distil an eval-certified workup trajectory into a structured analytic skill (ADR-0029).

The deterministic distiller: it *records* a certified trajectory into a structured skill
(``SKILL.md`` + ``skill-card.toml``). The gate is the keystone — only a run the eval
harness certified as ``grounded`` is a skill source (the external verifiable reward).
"""

from __future__ import annotations

import tomllib

import pytest

from ariadne.learning.distil import (
    NotCertified,
    RunArtifacts,
    distil_deterministic,
    distil_with_llm,
    granularity,
    load_run,
    phase_of,
    prerequisites,
    tool_family,
    write_skill,
)

# A small, real-shaped trajectory: graph schema -> relational lookup -> graph traversal
# -> full-text evidence, across the graph + relational + semantic capabilities.
_TRAJECTORY = [
    {"id": "g1", "tool": "mcp__postgres__list_schemas", "tool_input": {}, "response_excerpt": "[]"},
    {
        "id": "g2",
        "tool": "mcp__neo4j__read_neo4j_cypher",
        "tool_input": {"query": "CALL db.labels() YIELD label RETURN collect(label) AS labels"},
        "response_excerpt": "[]",
    },
    {
        "id": "g3",
        "tool": "mcp__postgres__execute_sql",
        "tool_input": {"sql": "SELECT * FROM personnel WHERE alias = 'H1'"},
        "response_excerpt": "[]",
    },
    {
        "id": "g4",
        "tool": "mcp__neo4j__read_neo4j_cypher",
        "tool_input": {"query": "MATCH (p:Person {name:'Halberd'})-[:MEMBER_OF]->(u) RETURN u"},
        "response_excerpt": "[]",
    },
    {
        "id": "g5",
        "tool": "mcp__ariadne__hybrid_search",
        "tool_input": {"query": "Halberd Signals-Cell Meridian Freight"},
        "response_excerpt": "[]",
    },
]

_EVAL_GROUNDED = {
    "entity": "Halberd",
    "recall": 1.0,
    "trajectory": 1.0,
    "grounded": True,
    "supporting_fact_f1": 1.0,
    "citation_coverage": 1.0,
    "context_utilization": 0.55,
    "fixture": "halberd",
}

_MANIFEST = {
    "run_id": "2026-06-07T15-33-41Z-b4f3e077",
    "entity": "Halberd",
    "dataset": "synthetic",
    "git_sha": "a98dd04",
}


def _run(
    *,
    trajectory: list[dict] | None = None,
    eval_scores: dict | None = None,
    manifest: dict | None = None,
    note: str = "# Note\nHalberd is the Signals-Cell lead [cite:g4].",
) -> RunArtifacts:
    return RunArtifacts(
        run_dir="runs/synthetic/halberd/2026-06-07T15-33-41Z-b4f3e077",
        provenance=_TRAJECTORY if trajectory is None else trajectory,
        eval_scores=_EVAL_GROUNDED if eval_scores is None else eval_scores,
        manifest=_MANIFEST if manifest is None else manifest,
        note=note,
    )


# --- the certification gate (the keystone) -----------------------------------------


def test_distil_rejects_run_that_did_not_ground() -> None:
    ungrounded = dict(_EVAL_GROUNDED, grounded=False)
    with pytest.raises(NotCertified):
        distil_deterministic(_run(eval_scores=ungrounded))


def test_distil_rejects_run_with_no_eval() -> None:
    # No fixture/eval => no external verifiable reward => not a skill source.
    with pytest.raises(NotCertified):
        distil_deterministic(_run(eval_scores={}))


def test_distil_with_llm_also_gates_on_certification() -> None:
    ungrounded = dict(_EVAL_GROUNDED, grounded=False)
    with pytest.raises(NotCertified):
        distil_with_llm(_run(eval_scores=ungrounded), call_llm=lambda _p: {})


# --- structural extraction ---------------------------------------------------------


def test_tool_family_maps_mcp_server_prefixes() -> None:
    assert tool_family("mcp__neo4j__read_neo4j_cypher") == "neo4j"
    assert tool_family("mcp__postgres__execute_sql") == "postgres"
    assert tool_family("mcp__ariadne__hybrid_search") == "ariadne"


def test_prerequisites_are_distinct_sorted_capabilities() -> None:
    # graph (neo4j) + relational (postgres) + semantic (ariadne hybrid_search)
    assert prerequisites(_run()) == ("graph", "relational", "semantic")


def test_granularity_composite_when_multiple_capabilities() -> None:
    assert granularity(("graph", "relational")) == "composite"


def test_granularity_atomic_when_single_capability() -> None:
    assert granularity(("graph",)) == "atomic"


def test_phase_categorizes_trajectory_entries() -> None:
    assert phase_of(_TRAJECTORY[0]) == "relational-schema"  # list_schemas
    assert phase_of(_TRAJECTORY[1]) == "graph-schema"  # CALL db.labels()
    assert phase_of(_TRAJECTORY[2]) == "relational-query"  # SELECT ... WHERE
    assert phase_of(_TRAJECTORY[3]) == "graph-traversal"  # MATCH ...-[:MEMBER_OF]->
    assert phase_of(_TRAJECTORY[4]) == "free-text"  # hybrid_search


def test_phase_treats_tsquery_sql_as_free_text() -> None:
    entry = {
        "id": "g9",
        "tool": "mcp__postgres__execute_sql",
        "tool_input": {
            "sql": "SELECT id FROM documents WHERE content_tsv @@ websearch_to_tsquery('x')"
        },
        "response_excerpt": "[]",
    }
    assert phase_of(entry) == "free-text"


# --- the deterministic skill -------------------------------------------------------


def test_deterministic_card_is_structured_and_auditable() -> None:
    skill = distil_deterministic(_run())
    card = skill.card
    assert card.granularity == "composite"
    assert card.prerequisites == ("graph", "relational", "semantic")
    assert card.distilled_by == "deterministic"
    # reliability carries the eval scores; the binary gate field is present and true
    assert card.reliability["grounded"] is True
    assert card.reliability["recall"] == 1.0
    # source provenance ties the skill to the exact run it was distilled from
    assert card.source["run_id"] == "2026-06-07T15-33-41Z-b4f3e077"
    assert card.source["dataset"] == "synthetic"
    assert card.source["entity"] == "Halberd"
    assert card.source["git_sha"] == "a98dd04"
    assert card.source["fixture"] == "halberd"


def test_default_skill_name_derives_from_dataset() -> None:
    assert distil_deterministic(_run()).card.name == "entity-workup-synthetic"
    assert distil_deterministic(_run(), name="cross-store-corroboration").card.name == (
        "cross-store-corroboration"
    )


def test_skill_md_has_spec_clean_frontmatter_and_cites_its_source() -> None:
    md = distil_deterministic(_run()).skill_md
    assert md.startswith("---\n")
    _, frontmatter, body = md.split("---\n", 2)
    assert "name: entity-workup-synthetic" in frontmatter
    assert "description:" in frontmatter
    # the body cites the exact source run + the certifying score (the citation ethos)
    assert "2026-06-07T15-33-41Z-b4f3e077" in body
    assert "grounded" in body.lower()
    # the observed move sequence names the phases it grouped
    assert "graph-traversal" in body
    assert "free-text" in body


def test_skill_card_toml_roundtrips_with_the_structured_keys() -> None:
    skill = distil_deterministic(_run())
    parsed = tomllib.loads(skill.card.to_toml())
    assert parsed["name"] == "entity-workup-synthetic"
    assert parsed["granularity"] == "composite"
    assert parsed["prerequisites"] == ["graph", "relational", "semantic"]
    assert parsed["reliability"]["grounded"] is True
    assert parsed["source"]["run_id"] == "2026-06-07T15-33-41Z-b4f3e077"
    assert parsed["distilled_by"] == "deterministic"


def test_write_skill_writes_skill_md_and_card_sidecar(tmp_path) -> None:
    skill = distil_deterministic(_run())
    out = write_skill(tmp_path, skill)
    assert out == tmp_path / "entity-workup-synthetic"
    assert (out / "SKILL.md").read_text(encoding="utf-8").startswith("---\n")
    card_text = (out / "skill-card.toml").read_text(encoding="utf-8")
    assert tomllib.loads(card_text)["name"] == "entity-workup-synthetic"


# --- load_run (the filesystem seam) ------------------------------------------------


def test_load_run_reads_the_persisted_artifacts(tmp_path) -> None:
    import json

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with (run_dir / "provenance.jsonl").open("w", encoding="utf-8") as fh:
        for entry in _TRAJECTORY:
            fh.write(json.dumps(entry) + "\n")
    (run_dir / "eval.json").write_text(json.dumps(_EVAL_GROUNDED), encoding="utf-8")
    (run_dir / "manifest.json").write_text(json.dumps(_MANIFEST), encoding="utf-8")
    (run_dir / "note.md").write_text("# Note\nbody", encoding="utf-8")

    run = load_run(run_dir)
    assert len(run.provenance) == len(_TRAJECTORY)
    assert run.eval_scores["grounded"] is True
    assert run.manifest is not None
    assert run.manifest["dataset"] == "synthetic"
    assert run.note.startswith("# Note")


def test_load_run_tolerates_a_run_without_eval(tmp_path) -> None:
    # A live workup with no fixture has no eval.json; load_run must not crash —
    # the certification gate (not load_run) is what refuses it.
    import json

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "provenance.jsonl").write_text(json.dumps(_TRAJECTORY[0]) + "\n", encoding="utf-8")
    (run_dir / "note.md").write_text("# Note", encoding="utf-8")
    run = load_run(run_dir)
    assert run.eval_scores == {}
    with pytest.raises(NotCertified):
        distil_deterministic(run)


# --- the --llm distiller (Trace2Skill generalization, hermetic via an injected seam) -


def test_distil_with_llm_generalizes_via_the_injected_call(tmp_path) -> None:
    proposed = {
        "name": "cross-store-entity-corroboration",
        "description": "Corroborate an entity across a graph and a relational store, then cite both.",
        "body": "## Procedure\n1. Locate the entity in each store.\n2. Match by shared key.\n",
    }
    seen: dict[str, str] = {}

    def fake_call(prompt: str) -> dict:
        seen["prompt"] = prompt
        return proposed

    skill = distil_with_llm(_run(), call_llm=fake_call, model="claude-opus-4-8")
    # the LLM's generalized name/description/body flow through
    assert skill.card.name == "cross-store-entity-corroboration"
    assert skill.card.description == proposed["description"]
    assert "Match by shared key" in skill.skill_md
    assert skill.card.distilled_by == "llm:claude-opus-4-8"
    # structure is still computed deterministically (not trusted to the model)
    assert skill.card.prerequisites == ("graph", "relational", "semantic")
    assert skill.card.reliability["grounded"] is True
    # the prompt grounded the model in the real trajectory + the certifying score
    assert "MEMBER_OF" in seen["prompt"]
    assert "grounded" in seen["prompt"].lower()


def test_distil_with_llm_name_override_wins(tmp_path) -> None:
    proposed = {"name": "x", "description": "d", "body": "b"}
    skill = distil_with_llm(_run(), call_llm=lambda _p: proposed, name="my-name")
    assert skill.card.name == "my-name"


def test_distil_with_llm_rejects_a_truncated_proposal() -> None:
    # A forced tool-call can return truncated (max_tokens) with the large `body` field
    # missing; surface a clear, actionable error, not a raw KeyError. (Caught live.)
    incomplete = {"name": "x", "description": "d"}  # no body
    with pytest.raises(RuntimeError, match="body"):
        distil_with_llm(_run(), call_llm=lambda _p: incomplete)


def _h1_count(md: str) -> int:
    return sum(1 for line in md.splitlines() if line.startswith("# "))


def test_deterministic_skill_md_has_exactly_one_h1() -> None:
    assert _h1_count(distil_deterministic(_run()).skill_md) == 1


def test_llm_skill_md_keeps_one_h1_when_the_body_brings_its_own() -> None:
    # LLM-proposed bodies usually open with their own H1 title; don't stack a second.
    proposed = {"name": "x", "description": "d", "body": "# My Title\n\n## Step\nbody"}
    md = distil_with_llm(_run(), call_llm=lambda _p: proposed).skill_md
    assert _h1_count(md) == 1
    assert "# My Title" in md
