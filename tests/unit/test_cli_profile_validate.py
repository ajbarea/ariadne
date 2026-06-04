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
