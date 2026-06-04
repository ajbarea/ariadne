from __future__ import annotations

import os
from typing import TYPE_CHECKING, cast

import ariadne.cli as cli
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


def test_main_without_api_key_exits_nonzero(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from any local .env
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rc = main(["workup", "Alpha"])
    assert rc != 0
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err


def test_main_autoloads_dotenv(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("ARIADNE_DOTENV_PROBE=loaded\n")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ARIADNE_DOTENV_PROBE", raising=False)
    try:
        # Returns 2 (no key) but must load .env into the environment first.
        assert main(["workup", "Alpha"]) == 2
        assert os.environ.get("ARIADNE_DOTENV_PROBE") == "loaded"
    finally:
        os.environ.pop("ARIADNE_DOTENV_PROBE", None)


def test_main_does_not_override_exported_env(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=from-dotenv\n")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-shell")

    async def _stub_run_workup(*_a: object, **_k: object) -> int:
        return 0  # don't launch the real agent

    monkeypatch.setattr(cli, "run_workup", _stub_run_workup)
    # load_dotenv(override=False) must not clobber the already-exported key.
    assert main(["workup", "Alpha"]) == 0
    assert os.environ["ANTHROPIC_API_KEY"] == "from-shell"


def test_workup_accepts_profile_flag() -> None:
    from ariadne.cli import parse_args

    args = parse_args(["workup", "Halberd", "--profile", "fast-local"])
    assert args.profile == "fast-local"


def test_workup_profile_defaults_to_default() -> None:
    from ariadne.cli import parse_args

    args = parse_args(["workup", "Halberd"])
    assert args.profile == "default"


def test_profiles_subcommand_parses() -> None:
    from ariadne.cli import parse_args

    args = parse_args(["profiles"])
    assert args.command == "profiles"
