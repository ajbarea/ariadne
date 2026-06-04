"""CLI surface for `ariadne rubric` and the workup `--entail` flag."""

from __future__ import annotations

import pytest

from ariadne.cli import main, parse_args


def test_workup_entail_flag_defaults_false() -> None:
    assert parse_args(["workup", "X"]).entail is False


def test_workup_entail_flag_opts_in() -> None:
    assert parse_args(["workup", "X", "--entail"]).entail is True


def test_rubric_requires_a_workup_dir() -> None:
    args = parse_args(["rubric", "./workups/halberd"])
    assert args.command == "rubric"
    assert args.workup_dir == "./workups/halberd"
    assert args.min is None  # informational by default; no pass/fail threshold


def test_rubric_accepts_a_min_threshold() -> None:
    args = parse_args(["rubric", "./workups/x", "--min", "3.5"])
    assert args.min == pytest.approx(3.5)


def test_rubric_without_api_key_exits_two(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from any local .env
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rc = main(["rubric", "./workups/x"])
    assert rc == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
