"""Net-effect ratification comparator — measure a learned artifact's effect (ADR-0031).

`compare` consumes two sides of eval'd runs (baseline vs candidate, on the SAME instance) and
nets repairs against regressions — the measured ratify step (you cannot tell a good skill by
reading it). It reads eval.json; it never recomputes a score.
"""

from __future__ import annotations

import pytest

from ariadne.learning.netcheck import (
    IncomparableRuns,
    compare,
    comparison_dict,
    render_comparison_md,
)
from ariadne.learning.runs import RunArtifacts


def _run(scores: dict, *, model: str = "claude-opus-4-8", profile: str = "default") -> RunArtifacts:
    return RunArtifacts(
        run_dir="runs/synthetic/halberd/R",
        provenance=[],
        eval_scores={"fixture": "halberd", **scores},
        manifest={"model": model, "profile": profile, "params": {"sql": True}},
        note="",
    )


_CLEAN = {
    "grounded": True,
    "recall": 1.0,
    "trajectory": 1.0,
    "supporting_fact_f1": 1.0,
    "citation_coverage": 1.0,
}


# --- the same-instance gate ---------------------------------------------------------


def test_compare_needs_both_sides() -> None:
    with pytest.raises(IncomparableRuns):
        compare([_run(_CLEAN)], [])


def test_compare_rejects_mixed_fixtures() -> None:
    base = _run(_CLEAN)
    cand = RunArtifacts(
        run_dir="r",
        provenance=[],
        eval_scores={"fixture": "wren-tie", **_CLEAN},
        manifest={},
        note="",
    )
    with pytest.raises(IncomparableRuns):
        compare([base], [cand])


# --- repair / regression / neutral verdicts -----------------------------------------


def test_regression_on_a_gated_dim_yields_reject() -> None:
    base = _run(_CLEAN)
    cand = _run({**_CLEAN, "grounded": False, "citation_coverage": 0.8})
    net = compare([base], [cand])
    assert net.regressions >= 1
    assert net.verdict == "reject"


def test_repair_yields_ratify() -> None:
    base = _run({**_CLEAN, "grounded": False, "citation_coverage": 0.8})
    cand = _run(_CLEAN)
    net = compare([base], [cand])
    assert net.repairs >= 1
    assert net.net > 0
    assert net.verdict == "ratify"


def test_identical_runs_are_neutral() -> None:
    net = compare([_run(_CLEAN)], [_run(_CLEAN)])
    assert net.repairs == 0 and net.regressions == 0
    assert net.net == 0
    assert net.verdict == "neutral"


def test_repairs_and_regressions_are_reported_separately() -> None:
    # candidate repairs recall but regresses citation_coverage (a gated dim): net 0, but the
    # gated regression forces reject — repair-rate alone would have hidden the break.
    base = _run({**_CLEAN, "recall": 0.5, "citation_coverage": 1.0})
    cand = _run({**_CLEAN, "recall": 1.0, "citation_coverage": 0.8})
    net = compare([base], [cand])
    assert net.repairs == 1
    assert net.regressions == 1
    assert net.net == 0
    assert net.verdict == "reject"  # hard-gated regression overrides a net-zero
    dims = {d.dimension: d.verdict for d in net.deltas}
    assert dims["recall"] == "repair"
    assert dims["citation_coverage"] == "regression"


# --- means over multiple trials -----------------------------------------------------


def test_means_are_taken_over_multiple_runs_per_side() -> None:
    base = [_run({**_CLEAN, "recall": 0.4}), _run({**_CLEAN, "recall": 0.6})]  # mean 0.5
    cand = [_run(_CLEAN), _run(_CLEAN)]  # mean 1.0
    net = compare(base, cand)
    recall = next(d for d in net.deltas if d.dimension == "recall")
    assert recall.baseline == 0.5
    assert recall.candidate == 1.0
    assert recall.verdict == "repair"
    assert net.n_baseline == 2 and net.n_candidate == 2


# --- caveats: stochasticity + harness disclosure ------------------------------------


def test_small_sample_caveat() -> None:
    net = compare([_run(_CLEAN)], [_run(_CLEAN)])
    assert any("stochastic" in c.lower() or "sample" in c.lower() for c in net.caveats)


def test_harness_mismatch_is_caveated() -> None:
    base = _run(_CLEAN, model="claude-opus-4-8")
    cand = _run(_CLEAN, model="claude-sonnet-4-6")
    net = compare([base], [cand])
    assert any("harness" in c.lower() or "model" in c.lower() for c in net.caveats)


# --- rendering ----------------------------------------------------------------------


def test_render_md_and_dict_carry_the_verdict() -> None:
    base = _run({**_CLEAN, "grounded": False, "citation_coverage": 0.8})
    net = compare([base], [_run(_CLEAN)])
    md = render_comparison_md(net)
    assert md.startswith("# ")
    assert "ratify" in md.lower()
    assert "repair" in md.lower()
    d = comparison_dict(net)
    assert d["verdict"] == "ratify"
    assert d["net"] == net.net
    assert isinstance(d["deltas"], list) and d["deltas"][0]["dimension"]


def test_compare_refuses_a_run_without_eval() -> None:
    base = RunArtifacts(run_dir="r", provenance=[], eval_scores={}, manifest={}, note="")
    with pytest.raises(IncomparableRuns):
        compare([base], [_run(_CLEAN)])
