from __future__ import annotations

from typing import TYPE_CHECKING, cast

from ariadne.cli import build_options, main, parse_args
from ariadne.graph.neo4j_server import GRAPH_TOOLS
from ariadne.provenance.ledger import ProvenanceLedger

if TYPE_CHECKING:
    from claude_agent_sdk.types import McpStdioServerConfig


def test_parse_args_defaults() -> None:
    ns = parse_args(["workup", "Alpha"])
    assert ns.command == "workup"
    assert ns.entity == "Alpha"
    assert ns.graph == "neo4j"
    assert ns.out == "./workups"


def test_parse_args_overrides() -> None:
    ns = parse_args(["workup", "Unit-7", "--out", "/tmp/x"])
    assert ns.entity == "Unit-7"
    assert ns.out == "/tmp/x"


def test_build_options_wires_graph_server_and_hook() -> None:
    led = ProvenanceLedger()
    opts = build_options(ledger=led, env={"NEO4J_URI": "bolt://x:7687"})
    assert opts.hooks is not None
    mcp = opts.mcp_servers
    assert isinstance(mcp, dict)
    assert "neo4j" in mcp
    server = cast("McpStdioServerConfig", mcp["neo4j"])
    assert server["env"]["NEO4J_READ_ONLY"] == "true"
    assert set(GRAPH_TOOLS).issubset(set(opts.allowed_tools or []))
    assert "PostToolUse" in opts.hooks
    assert opts.skills == ["entity-workup"]


def test_main_without_api_key_exits_nonzero(monkeypatch, capsys) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rc = main(["workup", "Alpha"])
    assert rc != 0
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
