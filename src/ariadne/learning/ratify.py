"""Automated net-effect ratification — produce the paired runs `compare` measures (ADR-0034).

`compare` ([ADR-0031]) nets a candidate artifact's repairs vs regressions on the same eval
instance, but a human must hand-produce the paired runs. `ratify` closes that gap: it stages two
arms (the candidate skill OFF vs ON), runs N trials of each over the same instance, scores each,
and feeds `compare`. Per SkillTester it also gates on an invocation check — if the candidate skill
never fired in the candidate arm, the measured delta is ambient model variance, not the skill, so
the verdict abstains rather than ratify.

The orchestration is hermetic: the live workup + scoring are *injected* seams (the CLI supplies the
real ones; tests supply fakes), so producing-and-measuring is testable without spending API.

# research(2026-06): counterfactual with-skill/without-skill paired runs, effect visible under
# saturation/cancellation (Counterfactual Trace Auditing, arXiv 2605.11946); matched baseline with
# the skill disabled + an invocation gate so ambient capability is not misattributed to the skill,
# ~14% help / ~78% no-effect / ~8% harm (SkillTester, arXiv 2603.28815). ADR-0034.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from ariadne.learning.netcheck import compare, render_comparison_md
from ariadne.learning.runs import load_run, skills_invoked

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ariadne.learning.netcheck import NetEffect
    from ariadne.learning.runs import RunArtifacts


@dataclass(frozen=True)
class ArmSpec:
    """One staged arm: a plugin directory the workup loads its skills from (ADR-0034)."""

    label: str  # "baseline" | "candidate"
    plugin_path: Path  # the plugin root — the parent of skills/, what the SDK `plugins=` wants


@dataclass(frozen=True)
class InvocationCheck:
    """Did the candidate skill actually fire in the candidate arm (the SkillTester gate)?"""

    expected: str
    observed: bool  # the expected skill fired in >= 1 candidate run
    signal_present: bool  # >= 1 candidate run recorded a skills_invoked signal at all
    note: str


@dataclass(frozen=True)
class RatifyOutcome:
    """The measured ratification evidence a human (or `--apply`) acts on."""

    net: NetEffect
    invocation: InvocationCheck
    baseline_runs: tuple[str, ...]
    candidate_runs: tuple[str, ...]
    verdict: str  # compare's verdict, downgraded to "abstain" if the invocation is confounded
    expected_skill: str


class ArmRunner(Protocol):
    """Run one workup for an arm and return its (existing) run dir."""

    def __call__(
        self, *, arm: ArmSpec, entity: str, dataset: str, env: dict[str, str], out_root: Path
    ) -> Path: ...


class ArmScorer(Protocol):
    """Score a run dir against the planted-needle fixture, persisting its eval.json."""

    def __call__(self, run_dir: Path, fixture: str) -> None: ...


def skill_name_of(skill_dir: str | Path) -> str:
    """The ``name:`` from a skill dir's ``SKILL.md`` frontmatter.

    Raises ``FileNotFoundError`` if there is no ``SKILL.md`` and ``ValueError`` if it carries no
    ``name:`` — the candidate's name is both its staged dir and the expected invocation, so an
    unnameable skill cannot be ratified.
    """
    md = (Path(skill_dir) / "SKILL.md").read_text(encoding="utf-8")
    parts = md.split("---", 2)
    block = parts[1] if len(parts) >= 3 and parts[0].strip() == "" else md
    m = re.search(r"^name:\s*(.+?)\s*$", block, re.MULTILINE)
    if not m:
        raise ValueError(f"{skill_dir}/SKILL.md has no `name:` frontmatter")
    return m.group(1).strip()


def _stage_plugin(root: Path, label: str, skills: dict[str, Path]) -> ArmSpec:
    skills_dir = root / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    for name, src in skills.items():
        shutil.copytree(src, skills_dir / name, dirs_exist_ok=True)
    return ArmSpec(label=label, plugin_path=root)


def stage_arms(
    candidate_skill: str | Path, base_skills: Sequence[str | Path], workdir: str | Path
) -> tuple[ArmSpec, ArmSpec]:
    """Stage the baseline (candidate OFF) and candidate (candidate ON) arms as plugin dirs.

    The candidate ON arm is the base skills with the proposal layered in — *replacing* a same-named
    base skill (a deepened ``entity-workup``) or *adding* a new one (a distilled aux skill). Both
    cases reduce to: drop any base skill the candidate shadows, then add the candidate.
    """
    candidate_skill = Path(candidate_skill)
    workdir = Path(workdir)
    cand_name = skill_name_of(candidate_skill)
    base_by_name = {skill_name_of(b): Path(b) for b in base_skills}

    baseline = _stage_plugin(workdir / "baseline", "baseline", base_by_name)
    cand_by_name = {n: p for n, p in base_by_name.items() if n != cand_name}
    cand_by_name[cand_name] = candidate_skill
    candidate = _stage_plugin(workdir / "candidate", "candidate", cand_by_name)
    return baseline, candidate


def check_invocation(candidate_runs: Sequence[RunArtifacts], expected: str) -> InvocationCheck:
    """Was ``expected`` actually invoked across the candidate arm (SkillTester confound control)?

    Three honest states: *observed* (proceed on compare's verdict); *signal present but never
    invoked* (the delta is ambient variance — the verdict must abstain); *no signal recorded* (the
    instrument is absent — a caveat, never a false reject, until recording is wired, ADR-0034).
    """
    present = [s for r in candidate_runs if (s := skills_invoked(r)) is not None]
    if not present:
        return InvocationCheck(
            expected,
            observed=False,
            signal_present=False,
            note=(
                "invocation signal not recorded by these runs — proceeding on the net-effect "
                "verdict; wire skill-invocation recording to gate on it (ADR-0034)."
            ),
        )
    if any(expected in s for s in present):
        return InvocationCheck(
            expected,
            observed=True,
            signal_present=True,
            note=f"`{expected}` fired in the candidate arm.",
        )
    return InvocationCheck(
        expected,
        observed=False,
        signal_present=True,
        note=(
            f"`{expected}` never fired across {len(present)} candidate run(s) that recorded skills "
            "— the measured delta is ambient model variance, not the skill (SkillTester)."
        ),
    )


def resolve_verdict(net: NetEffect, invocation: InvocationCheck) -> str:
    """compare's verdict, downgraded to ``abstain`` when the invocation is a confirmed confound."""
    if invocation.signal_present and not invocation.observed:
        return "abstain"
    return net.verdict


def _run_arm(
    arm: ArmSpec,
    *,
    n: int,
    entity: str,
    dataset: str,
    fixture: str,
    env: dict[str, str],
    out_root: Path,
    runner: ArmRunner,
    scorer: ArmScorer,
) -> list[Path]:
    dirs: list[Path] = []
    for _ in range(n):
        run_dir = Path(runner(arm=arm, entity=entity, dataset=dataset, env=env, out_root=out_root))
        scorer(run_dir, fixture)  # the eval is the single scorer; compare only reads its output
        dirs.append(run_dir)
    return dirs


def run_ratify(
    *,
    candidate_skill: str | Path,
    entity: str,
    dataset: str,
    fixture: str,
    n: int,
    env: dict[str, str],
    out_root: str | Path,
    base_skills: Sequence[str | Path],
    runner: ArmRunner,
    scorer: ArmScorer,
    workdir: str | Path | None = None,
) -> RatifyOutcome:
    """Produce the paired runs, measure them through `compare`, and gate on the invocation check.

    Runs ``n`` trials of each arm over the same ``(dataset, entity, fixture)`` instance via the
    injected ``runner`` + ``scorer``, then nets the candidate's effect. The eval stays the single
    scorer (each run scored once); `compare` only reads the scores (ADR-0020 boundary).
    """
    candidate_skill = Path(candidate_skill)
    out_root = Path(out_root)
    workdir = (
        Path(workdir) if workdir is not None else Path(tempfile.mkdtemp(prefix="ariadne-ratify-"))
    )
    expected = skill_name_of(candidate_skill)
    baseline_arm, candidate_arm = stage_arms(candidate_skill, base_skills, workdir)

    common = {"n": n, "entity": entity, "dataset": dataset, "fixture": fixture, "env": env}
    baseline_dirs = _run_arm(
        baseline_arm, **common, out_root=out_root, runner=runner, scorer=scorer
    )
    candidate_dirs = _run_arm(
        candidate_arm, **common, out_root=out_root, runner=runner, scorer=scorer
    )

    candidate_runs = [load_run(d) for d in candidate_dirs]
    net = compare([load_run(d) for d in baseline_dirs], candidate_runs)
    invocation = check_invocation(candidate_runs, expected)
    return RatifyOutcome(
        net=net,
        invocation=invocation,
        baseline_runs=tuple(str(d) for d in baseline_dirs),
        candidate_runs=tuple(str(d) for d in candidate_dirs),
        verdict=resolve_verdict(net, invocation),
        expected_skill=expected,
    )


def apply_ratification(
    candidate_skill: str | Path, *, skills_root: str | Path = Path(".claude/skills")
) -> Path:
    """Freeze the candidate: copy it under ``skills_root/<name>``, replacing any same-named skill.

    The opt-in freeze of propose → ratify → freeze — performed only on a clean ratify with a
    confirmed (or unobserved) invocation (the gate is the caller's, ADR-0034). Replacing an existing
    skill is the point for a deepened one; `.claude/skills/` is git-tracked, so the swap is recoverable.
    """
    candidate_skill = Path(candidate_skill)
    dest = Path(skills_root) / skill_name_of(candidate_skill)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(candidate_skill, dest)
    return dest


def render_ratification_md(outcome: RatifyOutcome) -> str:
    """The human-facing ratification verdict: the gate decision over the net-effect detail."""
    head = [
        f"# Ratification — verdict: {outcome.verdict.upper()}",
        "",
        f"Candidate skill `{outcome.expected_skill}`. Invocation: {outcome.invocation.note}",
    ]
    if outcome.verdict == "abstain":
        head.append(
            "The net-effect below does not reject, but the invocation gate abstains — the skill "
            "did not fire, so the measured delta is not its effect (SkillTester)."
        )
    return "\n".join([*head, "", render_comparison_md(outcome.net)])
