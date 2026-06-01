"""Build the stdio config for the official ``mcp-neo4j-cypher`` server.

We expose Neo4j as a read-only MCP tool family. The server provides schema
introspection, query timeouts, and token-aware truncation — the governance
guardrails the brief requires — so we never hand-roll Cypher execution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from claude_agent_sdk.types import McpStdioServerConfig

# Server pinned in pyproject; launched on demand via uvx for a clean subprocess.
_SERVER_SPEC = "mcp-neo4j-cypher@0.6.0"

# Read-only tool family the agent is allowed to call (write tool excluded entirely).
GRAPH_TOOLS = [
    "mcp__neo4j__get_neo4j_schema",
    "mcp__neo4j__read_neo4j_cypher",
]


def neo4j_stdio_config(env: dict[str, str]) -> McpStdioServerConfig:
    """Return an McpStdioServerConfig dict for the read-only Neo4j MCP server.

    ``env`` is typically ``os.environ``. Connection settings fall back to the
    server's local defaults; read-only is enforced via both the ``--read-only``
    flag and the ``NEO4J_READ_ONLY`` env var (defense-in-depth).
    """
    server_env = {
        "NEO4J_URI": env.get("NEO4J_URI", "bolt://localhost:7687"),
        "NEO4J_USERNAME": env.get("NEO4J_USERNAME", "neo4j"),
        "NEO4J_PASSWORD": env.get("NEO4J_PASSWORD", "password"),
        "NEO4J_DATABASE": env.get("NEO4J_DATABASE", "neo4j"),
        "NEO4J_READ_ONLY": "true",
        "NEO4J_READ_TIMEOUT": env.get("NEO4J_READ_TIMEOUT", "30"),
    }
    return {
        "type": "stdio",
        "command": "uvx",
        "args": [_SERVER_SPEC, "--transport", "stdio", "--read-only"],
        "env": server_env,
    }
