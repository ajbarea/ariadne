from __future__ import annotations

from ariadne.cli import build_options
from ariadne.graph.neo4j_server import GRAPH_TOOLS
from ariadne.provenance.ledger import ProvenanceLedger
from ariadne.relational.postgres_server import RELATIONAL_TOOLS


def test_graph_only_by_default() -> None:
    cfg = build_options(ledger=ProvenanceLedger(), env={})
    servers, hooks = cfg.mcp_servers, cfg.hooks
    assert isinstance(servers, dict) and isinstance(hooks, dict)
    assert set(servers) == {"neo4j"}
    assert cfg.allowed_tools == list(GRAPH_TOOLS)
    assert [m.matcher for m in hooks["PostToolUse"]] == ["mcp__neo4j__.*"]


def test_with_sql_adds_postgres_store_tools_and_hook() -> None:
    cfg = build_options(ledger=ProvenanceLedger(), env={}, with_sql=True)
    servers, hooks = cfg.mcp_servers, cfg.hooks
    assert isinstance(servers, dict) and isinstance(hooks, dict)
    assert set(servers) == {"neo4j", "postgres"}
    for tool in (*GRAPH_TOOLS, *RELATIONAL_TOOLS):
        assert tool in (cfg.allowed_tools or [])
    assert {m.matcher for m in hooks["PostToolUse"]} == {"mcp__neo4j__.*", "mcp__postgres__.*"}
