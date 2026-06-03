"""Build the stdio config for the ``postgres-mcp`` ("Postgres MCP Pro") server.

We expose a relational store as a read-only MCP tool family, in **Restricted
Mode** — read-only transactions with execution-time caps, and SQL parsed with
``pglast`` before execution to reject COMMIT/ROLLBACK statement-stacking. This is
the same official-guardrailed-server-over-hand-rolled call as the graph
connector: do not re-implement security-critical read-only enforcement.

# research(2026-06): crystaldba/postgres-mcp in --access-mode=restricted is the
# safest documented way to expose Postgres to an agent; the official
# @modelcontextprotocol/server-postgres reference server had a read-only-bypass
# SQL-injection via statement-stacking (Datadog Security Labs). See
# docs/research/best-practice-architecture.md / ROADMAP Phase 2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from claude_agent_sdk.types import McpStdioServerConfig

# Launched on demand via uvx; version pinned here (the functional source of truth).
_SERVER_SPEC = "postgres-mcp@0.3.0"

# research(2026-06): postgres-mcp pins pglast==7.2, which ships no wheel for
# Python 3.14 (too new) and fails to build from source — so the server is run
# under 3.13, where pglast has a wheel. The MCP server is an isolated uvx
# subprocess, so this is independent of the interpreter running Ariadne itself.
_SERVER_PYTHON = "3.13"

_DEFAULT_DATABASE_URI = "postgresql://ariadne:ariadne@localhost:5432/intel"

# Read-only retrieval subset the agent may call. Schema introspection + read
# queries only — the DBA/perf tools (analyze_*, get_top_queries, db_health) are
# out of scope for sensemaking and excluded (least privilege).
RELATIONAL_TOOLS = [
    "mcp__postgres__list_schemas",
    "mcp__postgres__list_objects",
    "mcp__postgres__get_object_details",
    "mcp__postgres__execute_sql",
]


def postgres_stdio_config(env: dict[str, str]) -> McpStdioServerConfig:
    """Return an McpStdioServerConfig for the restricted (read-only) Postgres MCP server.

    ``env`` is typically ``os.environ``. The connection string comes from
    ``DATABASE_URI`` (falling back to the local compose default); read-only is
    enforced by ``--access-mode=restricted`` plus the tool allowlist above.
    """
    return {
        "type": "stdio",
        "command": "uvx",
        "args": ["--python", _SERVER_PYTHON, _SERVER_SPEC, "--access-mode=restricted"],
        "env": {"DATABASE_URI": env.get("DATABASE_URI", _DEFAULT_DATABASE_URI)},
    }
