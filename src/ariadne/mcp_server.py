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
import shutil
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from ariadne.runs import slug as entity_slug

mcp = FastMCP(
    "ariadne",
    instructions="Rigorous, citation-grounded entity sensemaking over heterogeneous "
    "stores. Use `workup` to produce a cited analytic note for a target entity.",
)

_Runner = Callable[..., Awaitable[int]]


async def run_workup_tool(
    entity: str,
    *,
    dataset: str = "synthetic",
    sql: bool = False,
    semantic: bool = False,
    profile: str = "default",
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
    created_tmp = out_root is None
    out_root = out_root or tempfile.mkdtemp(prefix="ariadne-mcp-")
    slug = slug or entity_slug(entity)
    try:
        await runner(
            entity,
            out_root,
            base_env,
            with_sql=sql,
            dataset=dataset,
            with_semantic=semantic,
            profile=profile,
        )
        note = Path(out_root) / dataset / slug / "latest" / "note.md"
        if note.exists():
            return note.read_text(encoding="utf-8")
        return f"Workup for {entity!r} produced no analytic note (check stores / API key)."
    finally:
        if created_tmp:
            shutil.rmtree(out_root, ignore_errors=True)


@mcp.tool()
async def workup(
    entity: str,
    dataset: str = "synthetic",
    sql: bool = False,
    semantic: bool = False,
    profile: str = "default",
) -> str:
    """Produce a rigorous, citation-grounded analytic note for a target entity.

    Traverses the graph + (optionally) relational and semantic stores, reconciles
    across sources, and returns a note where every fact carries a [cite:gN] source.
    The ``profile`` selects the model + operating envelope from the deployment's
    curated allowlist (see ``list_profiles``).
    """
    return await run_workup_tool(
        entity, dataset=dataset, sql=sql, semantic=semantic, profile=profile
    )


@mcp.tool()
async def list_profiles() -> dict[str, Any]:
    """List the model profiles this deployment offers (the curated allowlist)."""
    from ariadne.profiles import load_profiles

    return {
        name: {"model": p.model, "egress": p.egress, "description": p.description}
        for name, p in load_profiles(dict(os.environ)).items()
    }


def list_datasets_info(env: dict[str, str]) -> dict[str, dict[str, str]]:
    """Every dataset a host agent can target: built-ins + ``$ARIADNE_MAPPINGS`` user mappings.

    Imports the built-in adapters for their registration side-effect (the MCP server is a
    separate entry point from the CLI, so they aren't otherwise loaded), then discovers any
    ratified user mappings under ``$ARIADNE_MAPPINGS`` (ADR-0025). Each name is a valid
    ``dataset`` argument to ``workup``. The enumeration seam dynamic per-dataset tool
    families (A3) will build on.
    """
    import ariadne.datasets.enron  # side-effect: register the built-in adapters
    import ariadne.datasets.lahman
    import ariadne.datasets.synthetic
    import ariadne.datasets.worldspeech  # noqa: F401  (last side-effect import; binds nothing read)
    from ariadne.datasets.base import DATASETS
    from ariadne.datasets.mapping_source import discover_and_register

    discover_and_register(env)
    return {
        name: {"entity_type": a.entity_type, "access": a.access}
        for name, a in sorted(DATASETS.items())
    }


@mcp.tool()
async def list_datasets() -> dict[str, Any]:
    """List the datasets this deployment can work up (built-ins + user-mapped stores).

    Each name is a valid ``dataset`` argument to ``workup``; ``access`` is "public" or
    "restricted". User stores ratified under ``$ARIADNE_MAPPINGS`` (ADR-0025) appear here
    once their mapping is in place.
    """
    return list_datasets_info(dict(os.environ))


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
    from ariadne.observability import setup_telemetry

    setup_telemetry()
    mcp.run()


if __name__ == "__main__":
    main()
