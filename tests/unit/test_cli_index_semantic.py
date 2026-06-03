"""Tests for ariadne index --semantic flag parsing."""

from __future__ import annotations

from ariadne.cli import parse_args


def test_index_semantic_flag_defaults_false() -> None:
    assert parse_args(["index"]).semantic is False


def test_index_semantic_flag_opts_in() -> None:
    assert parse_args(["index", "--semantic"]).semantic is True
