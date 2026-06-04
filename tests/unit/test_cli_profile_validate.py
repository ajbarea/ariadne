from __future__ import annotations

from dataclasses import dataclass

from ariadne.cli import _validate_profile


@dataclass
class _FakeReport:
    grounded: bool
    recall: float = 1.0
    trajectory: float = 1.0


async def _fast_runner(entity, out_root, env, **kw) -> int:
    return 0


async def _slow_runner(entity, out_root, env, **kw) -> int:
    import asyncio

    await asyncio.sleep(5)
    return 0


def test_validate_passes_when_grounded() -> None:
    rc = _validate_profile(
        "default", env={}, runner=_fast_runner, scorer=lambda d: _FakeReport(True)
    )
    assert rc == 0


def test_validate_fails_when_not_grounded() -> None:
    rc = _validate_profile(
        "default", env={}, runner=_fast_runner, scorer=lambda d: _FakeReport(False)
    )
    assert rc == 1


def test_validate_fails_on_timeout() -> None:
    rc = _validate_profile(
        "default", env={}, timeout=0.05, runner=_slow_runner, scorer=lambda d: _FakeReport(True)
    )
    assert rc == 1


def test_validate_rejects_unknown_profile() -> None:
    import pytest

    with pytest.raises(ValueError, match="Valid profiles"):
        _validate_profile("bogus", env={}, runner=_fast_runner, scorer=lambda d: _FakeReport(True))


def test_validate_runs_every_dataset_case_by_default() -> None:
    seen: list[str] = []

    async def _counting_runner(entity, out_root, env, **kw) -> int:
        seen.append(kw["dataset"])
        return 0

    rc = _validate_profile(
        "default", env={}, runner=_counting_runner, scorer=lambda d: _FakeReport(True)
    )
    assert rc == 0
    assert set(seen) == {"synthetic", "enron"}  # both registered cases ran


def test_validate_restricts_to_one_dataset() -> None:
    seen: list[str] = []

    async def _counting_runner(entity, out_root, env, **kw) -> int:
        seen.append(kw["dataset"])
        return 0

    rc = _validate_profile(
        "default",
        env={},
        dataset="synthetic",
        runner=_counting_runner,
        scorer=lambda d: _FakeReport(True),
    )
    assert rc == 0
    assert seen == ["synthetic"]  # only the requested dataset ran


def test_validate_fails_overall_if_any_dataset_fails() -> None:
    async def _runner(entity, out_root, env, **kw) -> int:
        return 0

    # synthetic grounds, enron does not -> overall FAIL
    def _scorer(out_dir: str) -> _FakeReport:
        return _FakeReport(grounded="halberd" in out_dir or "Halberd" in out_dir)

    rc = _validate_profile("default", env={}, runner=_runner, scorer=_scorer)
    assert rc == 1
