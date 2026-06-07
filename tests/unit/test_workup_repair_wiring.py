"""CLI surface for the post-hoc citation repair pass (ADR-0022).

The repair pass must be tool-less (it can only rewrite text, never retrieve or
mutate the evidence stores), and it is on by default with a --no-repair escape
hatch that doubles as the raw-G-Cite eval lever.
"""

from __future__ import annotations

from ariadne.cli import build_repair_options, parse_args


def test_repair_options_are_tool_less() -> None:
    opts = build_repair_options("claude-opus-4-1")
    assert opts.mcp_servers == {}
    assert list(opts.allowed_tools) == []


def test_repair_flag_defaults_on() -> None:
    assert parse_args(["workup", "Halberd"]).repair is True


def test_repair_flag_can_be_disabled() -> None:
    assert parse_args(["workup", "Halberd", "--no-repair"]).repair is False
