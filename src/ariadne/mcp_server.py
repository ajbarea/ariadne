"""Ariadne as an MCP server — usable from any MCP client (ADR-0009).

Exposes the whole harness as a single ``workup`` tool: a host agent (Claude
Code, Copilot, Gemini CLI, Cursor, ...) calls it and Ariadne runs its own
gather->act->verify->synthesize loop internally, returning the cited analytic note.
A ``hybrid_search`` tool is offered for composition. Run as ``ariadne-mcp``
(stdio) or ``python -m ariadne.mcp_server``.

Config caveat: the tool is portable, the data is not -- point the server at your
stores (NEO4J_*/DATABASE_URI) + ANTHROPIC_API_KEY per install.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "ariadne",
    instructions="Rigorous, citation-grounded entity sensemaking over heterogeneous "
    "stores. Use `workup` to produce a cited analytic note for a target entity.",
)

_Runner = Callable[..., Awaitable[int]]


def _slug(entity: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in entity).strip("-").lower() or "entity"


async def run_workup_tool(
    entity: str,
    *,
    dataset: str = "synthetic",
    sql: bool = False,
    semantic: bool = False,
    env: dict[str, str] | None = None,
    runner: _Runner | None = None,
    out_root: str | None = None,
    slug: str | None = None,
) -> str:
    """Run a workup and return the cited note text (testable core, DI'd runner)."""
    if runner is None:
        from ariadne.cli import run_workup

        runner = run_workup
    base_env = dict(os.environ) if env is None else dict(env)
    out_root = out_root or tempfile.mkdtemp(prefix="ariadne-mcp-")
    slug = slug or _slug(entity)
    await runner(entity, out_root, base_env, with_sql=sql, dataset=dataset, with_semantic=semantic)
    note = Path(out_root) / slug / "note.md"
    if note.exists():
        return note.read_text(encoding="utf-8")
    return f"Workup for {entity!r} produced no analytic note (check stores / API key)."


@mcp.tool()
async def workup(
    entity: str, dataset: str = "synthetic", sql: bool = False, semantic: bool = False
) -> str:
    """Produce a rigorous, citation-grounded analytic note for a target entity.

    Traverses the graph + (optionally) relational and semantic stores, reconciles
    across sources, and returns a note where every fact carries a [cite:gN] source.
    """
    return await run_workup_tool(entity, dataset=dataset, sql=sql, semantic=semantic)


@mcp.tool()
async def hybrid_search(query: str, limit: int = 5) -> dict[str, Any]:
    """Full-text + semantic (RRF) search over indexed email-body documents."""
    import psycopg

    from ariadne.unstructured.embed import SentenceTransformerEmbedder
    from ariadne.unstructured.search_tool import _format_content, search_documents

    dsn = os.environ.get("DATABASE_URI", "postgresql://ariadne:ariadne@localhost:5432/intel")
    with psycopg.connect(dsn, autocommit=True) as conn:
        results = search_documents(conn, query, SentenceTransformerEmbedder(), limit=limit)
    return _format_content(results)


def main() -> None:
    """Entry point -- runs the stdio MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
