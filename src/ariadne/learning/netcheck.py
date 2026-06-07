"""Net-effect ratification comparator — measure a learned artifact's effect (ADR-0031).

The measured ratify step of propose -> ratify -> freeze: you cannot tell a good skill from
its prose (negative transfer hits ~25% of skills), so `compare` nets a candidate's **repairs**
against its **regressions** versus a baseline, on the SAME eval instance. It only reads the
existing `eval.json`; it never recomputes a score (the eval stays the single scorer, ADR-0020).

# research(2026-06): SkillGen verifier-gate on net gain (arXiv 2605.10999); you cannot identify
# bad skills by reading them, negative transfer ~25% (SkillLens/SkillOpt arXiv 2605.23904);
# net-effect = repairs - regressions, not repair-rate (arXiv 2511.11012); paired same-instance
# comparison reduces variance in stochastic agentic eval (arXiv 2512.06710); disclose the harness
# (arXiv 2605.23950). ADR-0031.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from ariadne.learning.runs import fmt_score

if TYPE_CHECKING:
    from ariadne.learning.runs import RunArtifacts

# Gold-anchored dimensions whose ideal (1.0) is known; grounded is taken as 1.0/0.0.
_GOLD = ("grounded", "recall", "trajectory", "supporting_fact_f1", "citation_coverage")
# Hard-gated dimensions: a regression here forces a reject regardless of the net count.
_GATED = ("grounded", "citation_coverage")
_MIN_TRIALS = 3  # below this per side, the verdict is directional only (stochastic eval)


class IncomparableRuns(Exception):
    """The two sides cannot be compared — empty, unscored, or different instances."""


@dataclass(frozen=True)
class DimDelta:
    """One dimension's baseline->candidate move and its classification."""

    dimension: str
    baseline: float
    candidate: float
    delta: float
    verdict: str  # "repair" | "regression" | "improvement" | "decline" | "neutral"


@dataclass(frozen=True)
class NetEffect:
    """The measured net effect — the ratification evidence a human acts on."""

    deltas: tuple[DimDelta, ...]
    repairs: int
    regressions: int
    net: int
    verdict: str  # "ratify" | "reject" | "neutral"
    caveats: list[str]
    n_baseline: int
    n_candidate: int


def _fixture(run: RunArtifacts) -> str:
    return run.eval_scores.get("fixture", "")


def _harness(run: RunArtifacts) -> tuple[Any, Any, str]:
    m = run.manifest or {}
    return (m.get("model"), m.get("profile"), json.dumps(m.get("params"), sort_keys=True))


def _mean_scores(runs: list[RunArtifacts]) -> dict[str, float]:
    """Per-dimension mean over the runs that carry it (grounded as 1.0/0.0)."""
    out: dict[str, float] = {}
    for dim in _GOLD:
        vals: list[float] = []
        for r in runs:
            v = r.eval_scores.get(dim)
            if isinstance(v, bool):
                vals.append(1.0 if v else 0.0)
            elif isinstance(v, (int, float)):
                vals.append(float(v))
        if vals:
            out[dim] = sum(vals) / len(vals)
    return out


def _classify(baseline: float, candidate: float, ideal: float = 1.0) -> str:
    if baseline < ideal <= candidate:
        return "repair"
    if candidate < ideal <= baseline:
        return "regression"
    if candidate > baseline:
        return "improvement"
    if candidate < baseline:
        return "decline"
    return "neutral"


def _caveats(baselines: list[RunArtifacts], candidates: list[RunArtifacts]) -> list[str]:
    out: list[str] = []
    if len(baselines) < _MIN_TRIALS or len(candidates) < _MIN_TRIALS:
        out.append(
            f"small sample (< {_MIN_TRIALS} runs per side): agentic eval is stochastic — treat "
            "the verdict as directional; paired same-instance trials tighten it."
        )
    if len({_harness(r) for r in [*baselines, *candidates]}) > 1:
        out.append(
            "the harness differs across the runs (model / profile / params) — the measured "
            "effect is confounded with the harness change; hold the harness constant."
        )
    return out


def compare(baselines: list[RunArtifacts], candidates: list[RunArtifacts]) -> NetEffect:
    """Net a candidate's repairs against its regressions vs a baseline, on the same instance.

    Raises :class:`IncomparableRuns` if a side is empty, a run is unscored, or the runs span
    more than one eval fixture (paired same-instance comparison is what makes the delta a signal).
    """
    if not baselines or not candidates:
        raise IncomparableRuns("need at least one baseline and one candidate run")
    for r in [*baselines, *candidates]:
        if not r.eval_scores:
            raise IncomparableRuns(f"run {r.run_dir} has no eval.json — score it first")
    fixtures = {_fixture(r) for r in [*baselines, *candidates]}
    if len(fixtures) > 1:
        raise IncomparableRuns(
            f"runs span multiple fixtures {sorted(fixtures)} — compare on the same instance"
        )

    base, cand = _mean_scores(baselines), _mean_scores(candidates)
    deltas: list[DimDelta] = []
    repairs = regressions = 0
    for dim in _GOLD:
        if dim not in base or dim not in cand:
            continue
        verdict = _classify(base[dim], cand[dim])
        deltas.append(DimDelta(dim, base[dim], cand[dim], cand[dim] - base[dim], verdict))
        repairs += verdict == "repair"
        regressions += verdict == "regression"

    net = repairs - regressions
    hard_regression = any(d.verdict == "regression" and d.dimension in _GATED for d in deltas)
    verdict = "reject" if (hard_regression or net < 0) else ("ratify" if net > 0 else "neutral")
    return NetEffect(
        deltas=tuple(deltas),
        repairs=repairs,
        regressions=regressions,
        net=net,
        verdict=verdict,
        caveats=_caveats(baselines, candidates),
        n_baseline=len(baselines),
        n_candidate=len(candidates),
    )


def render_comparison_md(net: NetEffect) -> str:
    lines = [
        f"# Net-effect comparison — verdict: {net.verdict.upper()}",
        "",
        f"{net.n_baseline} baseline vs {net.n_candidate} candidate run(s) on the same instance. "
        f"Repairs {net.repairs}, regressions {net.regressions}, net {net.net:+d}.",
        "",
        "## Per-dimension",
        "",
    ]
    lines.extend(
        f"- **{d.dimension}**: {fmt_score(d.baseline)} -> {fmt_score(d.candidate)} "
        f"({d.delta:+.3f}) · {d.verdict}"
        for d in net.deltas
    )
    if net.caveats:
        lines += ["", "## Caveats", "", *[f"- {c}" for c in net.caveats]]
    return "\n".join(lines) + "\n"


def comparison_dict(net: NetEffect) -> dict[str, Any]:
    return {
        "verdict": net.verdict,
        "repairs": net.repairs,
        "regressions": net.regressions,
        "net": net.net,
        "n_baseline": net.n_baseline,
        "n_candidate": net.n_candidate,
        "deltas": [asdict(d) for d in net.deltas],
        "caveats": net.caveats,
    }
