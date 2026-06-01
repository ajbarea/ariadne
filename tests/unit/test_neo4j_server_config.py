from __future__ import annotations

from ariadne.graph.neo4j_server import GRAPH_TOOLS, neo4j_stdio_config


def test_config_defaults_to_read_only_and_stdio() -> None:
    cfg = neo4j_stdio_config(env={})
    assert cfg["type"] == "stdio"
    assert cfg["command"] == "uvx"
    assert "--transport" in cfg["args"] and "stdio" in cfg["args"]
    assert "--read-only" in cfg["args"]
    assert cfg["env"]["NEO4J_READ_ONLY"] == "true"
    assert cfg["env"]["NEO4J_URI"] == "bolt://localhost:7687"


def test_config_reads_connection_from_env() -> None:
    cfg = neo4j_stdio_config(
        env={
            "NEO4J_URI": "bolt://db:7687",
            "NEO4J_USERNAME": "reader",
            "NEO4J_PASSWORD": "secret",
            "NEO4J_DATABASE": "intel",
        }
    )
    assert cfg["env"]["NEO4J_URI"] == "bolt://db:7687"
    assert cfg["env"]["NEO4J_USERNAME"] == "reader"
    assert cfg["env"]["NEO4J_PASSWORD"] == "secret"  # noqa: S105
    assert cfg["env"]["NEO4J_DATABASE"] == "intel"


def test_graph_tools_are_read_only() -> None:
    assert "mcp__neo4j__read_neo4j_cypher" in GRAPH_TOOLS
    assert "mcp__neo4j__get_neo4j_schema" in GRAPH_TOOLS
    assert all("write" not in t for t in GRAPH_TOOLS)
