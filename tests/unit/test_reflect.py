"""Reflexion over the eval harness — diagnose + reflect, grounded and gold-free (ADR-0030).

B3: an eval-triggered reflection that diagnoses a run's underperforming dimensions and
proposes refinements, grounded in the agent's OWN evidence — never the held-out fixture gold
(the train/test-leakage reward-hacking vector). Propose-only; a human ratifies.
"""

from __future__ import annotations

import inspect
import json

import pytest

from ariadne.learning.reflect import (
    NoReward,
    diagnose,
    reflect_deterministic,
    reflect_with_llm,
    write_reflection,
)
from ariadne.learning.runs import RunArtifacts

_TRAJECTORY = [
    {
        "id": "g1",
        "tool": "mcp__neo4j__read_neo4j_cypher",
        "tool_input": {"query": "CALL db.labels()"},
    },
    {
        "id": "g2",
        "tool": "mcp__postgres__execute_sql",
        "tool_input": {"sql": "SELECT * FROM personnel WHERE alias = 'H1'"},
    },
]

_MANIFEST = {"run_id": "R1", "dataset": "synthetic", "entity": "Halberd", "git_sha": "abc"}


def _run(*, eval_scores=None, citations=None, provenance=None) -> RunArtifacts:
    return RunArtifacts(
        run_dir="runs/synthetic/halberd/R1",
        provenance=_TRAJECTORY if provenance is None else provenance,
        eval_scores={"entity": "Halberd", "fixture": "halberd"}
        if eval_scores is None
        else eval_scores,
        manifest=_MANIFEST,
        note="# Note\nbody [cite:g2].",
        citations=citations,
    )


# --- the gate: reflection needs the external verifiable reward ----------------------


def test_diagnose_refuses_a_run_without_eval() -> None:
    with pytest.raises(NoReward):
        diagnose(_run(eval_scores={}))


def test_reflect_deterministic_also_gates_on_the_reward() -> None:
    with pytest.raises(NoReward):
        reflect_deterministic(_run(eval_scores={}))


# --- a clean run yields no findings (no invented defects) ---------------------------


def test_a_perfect_run_yields_no_findings() -> None:
    perfect = {
        "grounded": True,
        "recall": 1.0,
        "trajectory": 1.0,
        "supporting_fact_f1": 1.0,
        "citation_coverage": 1.0,
        "fixture": "halberd",
    }
    assert diagnose(_run(eval_scores=perfect, citations={"uncited": [], "dangling": []})) == []


# --- own-evidence findings: citation failures cite the agent's OWN claims ------------


def test_low_citation_coverage_is_an_own_evidence_finding() -> None:
    ev = {"grounded": False, "citation_coverage": 0.83, "fixture": "halberd"}
    cites = {
        "uncited": ["Halberd commands the Eastern cell."],
        "dangling": ["g9"],
        "unsupported": [],
    }
    findings = diagnose(_run(eval_scores=ev, citations=cites))
    cite_finding = next(f for f in findings if f.dimension == "citation_coverage")
    assert cite_finding.kind == "own-evidence"
    assert cite_finding.score == 0.83
    # the evidence is the agent's own uncited/dangling claims (gold-free)
    joined = " ".join(cite_finding.evidence)
    assert "Halberd commands the Eastern cell." in joined
    assert "g9" in joined


# --- score-triggered findings: gold-anchored dims grounded in trajectory SHAPE -------


def test_low_recall_is_score_triggered_and_grounded_in_trajectory_shape() -> None:
    ev = {"grounded": True, "recall": 0.5, "citation_coverage": 1.0, "fixture": "halberd"}
    findings = diagnose(_run(eval_scores=ev, citations={"uncited": []}))
    recall = next(f for f in findings if f.dimension == "recall")
    assert recall.kind == "score-triggered"
    assert recall.ideal == 1.0
    # evidence is the agent's own trajectory shape — capabilities/phases, never the gold
    joined = " ".join(recall.evidence).lower()
    assert "capabilities used" in joined
    assert "graph" in joined and "relational" in joined


# --- behavioral findings: exact-duplicate queries (non-arbitrary, gold-free) ---------


def test_duplicate_queries_are_a_behavioral_finding() -> None:
    dup_traj = [
        {
            "id": "g1",
            "tool": "mcp__neo4j__read_neo4j_cypher",
            "tool_input": {"query": "MATCH (n) RETURN n"},
        },
        {
            "id": "g2",
            "tool": "mcp__neo4j__read_neo4j_cypher",
            "tool_input": {"query": "MATCH (n) RETURN n"},
        },
    ]
    ev = {"grounded": True, "recall": 1.0, "citation_coverage": 1.0, "fixture": "halberd"}
    findings = diagnose(_run(eval_scores=ev, provenance=dup_traj, citations={"uncited": []}))
    dup = next(f for f in findings if f.dimension == "redundant-queries")
    assert dup.kind == "behavioral"
    assert "g1" in " ".join(dup.evidence) and "g2" in " ".join(dup.evidence)


# --- the gold-free structural invariant ---------------------------------------------


def test_reflect_module_never_reads_the_fixture_gold() -> None:
    # The train/test-leakage reward-hacking vector: reflection must never touch the held-out
    # answer key. Enforce it structurally — the module does not reference the fixture gold.
    import ariadne.learning.reflect as reflect_mod

    src = inspect.getsource(reflect_mod)
    assert "FIXTURES" not in src
    assert "import" in src and "needle" not in src  # never imports the fixture module


# --- deterministic reflection rendering ---------------------------------------------


def test_deterministic_reflection_renders_findings_and_context() -> None:
    ev = {
        "grounded": False,
        "citation_coverage": 0.83,
        "recall": 0.5,
        "context_utilization": 0.4,
        "pivot_burden": 6.5,
        "fixture": "halberd",
    }
    cites = {"uncited": ["An uncited assertion."], "dangling": []}
    reflection = reflect_deterministic(_run(eval_scores=ev, citations=cites))
    md = reflection.reflection_md
    assert md.startswith("# Reflection")
    assert "citation_coverage" in md and "recall" in md
    # descriptive dims are reported as context with the never-gated caveat (ADR-0019)
    assert "context_utilization" in md
    assert "never-gated" in md.lower() or "ADR-0019" in md
    assert reflection.structured["reflected_by"] == "deterministic"
    assert reflection.structured["gold_free"] is True
    assert len(reflection.findings) >= 2


def test_clean_run_reflection_says_nothing_to_refine() -> None:
    perfect = {
        "grounded": True,
        "recall": 1.0,
        "trajectory": 1.0,
        "supporting_fact_f1": 1.0,
        "citation_coverage": 1.0,
        "fixture": "halberd",
    }
    reflection = reflect_deterministic(_run(eval_scores=perfect, citations={"uncited": []}))
    assert reflection.findings == ()
    assert "nothing to refine" in reflection.reflection_md.lower()


# --- the --llm reflexion (hermetic via an injected seam) -----------------------------


def test_reflect_with_llm_runs_the_reflexion_over_the_findings() -> None:
    ev = {"grounded": False, "citation_coverage": 0.8, "fixture": "halberd"}
    cites = {"uncited": ["Halberd runs the Eastern cell."], "dangling": []}
    seen: dict[str, str] = {}

    def fake_call(prompt: str) -> dict:
        seen["prompt"] = prompt
        return {
            "reflection": "## Post-mortem\nTighten the citation step.\n## Proposal\nCite claim X."
        }

    reflection = reflect_with_llm(
        _run(eval_scores=ev, citations=cites), call_llm=fake_call, model="claude-opus-4-8"
    )
    assert "Tighten the citation step" in reflection.reflection_md
    assert reflection.structured["reflected_by"] == "llm:claude-opus-4-8"
    # the prompt was grounded in the agent's OWN uncited claim, not any gold
    assert "Halberd runs the Eastern cell." in seen["prompt"]


def test_reflect_with_llm_rejects_an_empty_proposal() -> None:
    # Truncation guard (the lesson from B2): a missing `reflection` field is a clear error.
    ev = {"grounded": False, "citation_coverage": 0.8, "fixture": "halberd"}
    cites = {"uncited": ["x"], "dangling": []}
    with pytest.raises(RuntimeError, match="reflection"):
        reflect_with_llm(_run(eval_scores=ev, citations=cites), call_llm=lambda _p: {})


def test_reflect_with_llm_short_circuits_a_clean_run() -> None:
    # No findings => no API call; deterministic "clean" reflection.
    perfect = {"grounded": True, "recall": 1.0, "citation_coverage": 1.0, "fixture": "halberd"}

    def explode(_prompt: str) -> dict:
        raise AssertionError("must not call the model when there is nothing to refine")

    reflection = reflect_with_llm(
        _run(eval_scores=perfect, citations={"uncited": []}), call_llm=explode
    )
    assert reflection.findings == ()
    assert reflection.structured["reflected_by"] == "deterministic"


# --- writing the reflection beside the run's artifacts ------------------------------


def test_write_reflection_writes_md_and_json(tmp_path) -> None:
    ev = {"grounded": False, "citation_coverage": 0.8, "fixture": "halberd"}
    reflection = reflect_deterministic(
        _run(eval_scores=ev, citations={"uncited": ["x"], "dangling": []})
    )
    md, js = write_reflection(tmp_path, reflection)
    assert md == tmp_path / "reflection.md"
    assert js == tmp_path / "reflection.json"
    assert md.read_text(encoding="utf-8").startswith("# Reflection")
    assert json.loads(js.read_text(encoding="utf-8"))["gold_free"] is True
