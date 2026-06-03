from __future__ import annotations

from ariadne.relational.postgres_server import RELATIONAL_TOOLS, postgres_stdio_config


def test_config_defaults_to_restricted_and_stdio() -> None:
    cfg = postgres_stdio_config(env={})
    assert cfg["type"] == "stdio"
    assert cfg["command"] == "uvx"
    assert "--access-mode=restricted" in cfg["args"]
    # pinned to a Python with pglast wheels (postgres-mcp's pglast has no py3.14 wheel)
    assert "--python" in cfg["args"]
    assert cfg["env"]["DATABASE_URI"].startswith("postgresql://")
    assert "localhost:5432" in cfg["env"]["DATABASE_URI"]


def test_config_reads_database_uri_from_env() -> None:
    cfg = postgres_stdio_config(env={"DATABASE_URI": "postgresql://reader:s@db:5432/intel"})
    assert cfg["env"]["DATABASE_URI"] == "postgresql://reader:s@db:5432/intel"


def test_relational_tools_are_read_only_retrieval() -> None:
    assert "mcp__postgres__execute_sql" in RELATIONAL_TOOLS
    assert "mcp__postgres__list_schemas" in RELATIONAL_TOOLS
    # least privilege: no DBA/perf/health tools, nothing obviously mutating
    forbidden = ("analyze", "top_queries", "health", "index", "write", "insert", "update", "delete")
    assert all(not any(f in tool for f in forbidden) for tool in RELATIONAL_TOOLS)
