from __future__ import annotations

from ariadne.cli import parse_args


def test_workup_semantic_flag_defaults_false() -> None:
    assert parse_args(["workup", "X"]).semantic is False


def test_workup_semantic_flag_opts_in() -> None:
    assert parse_args(["workup", "X", "--semantic"]).semantic is True
