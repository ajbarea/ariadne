"""In-process hybrid-search tool for the live agent loop (ADR-0007 / B3.2).

Exposes ``mcp__ariadne__hybrid_search`` so the agent can semantically + lexically
search email-body Documents (RRF-fused) and cite the results like any other
evidence. The DB connection is opened per call from ``DATABASE_URI``; the
embedder is injected.
"""

from __future__ import annotations

from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from ariadne.unstructured.document_store import hybrid_search

ARIADNE_TOOLS = ["mcp__ariadne__hybrid_search"]
_DEFAULT_DSN = "postgresql://ariadne:ariadne@localhost:5432/intel"
_SNIPPET = 1000


def search_documents(conn, query: str, embedder, *, limit: int = 5) -> list[dict]:
    """RRF-fused ids (B3.1) joined back to their text, preserving rank order."""
    ids = hybrid_search(conn, query, embedder, limit=limit)
    if not ids:
        return []
    rows = conn.execute(
        b"SELECT id, text FROM documents WHERE id = ANY(%(ids)s)", {"ids": ids}
    ).fetchall()
    by_id = {r[0]: r[1] for r in rows}
    return [{"id": i, "text": by_id.get(i, "")} for i in ids]


def _format_content(results: list[dict]) -> dict[str, Any]:
    if not results:
        return {"content": [{"type": "text", "text": "No matching documents."}]}
    blocks = [f"[{r['id']}] {r['text'][:_SNIPPET]}" for r in results]
    return {"content": [{"type": "text", "text": "\n\n".join(blocks)}]}


def make_ariadne_server(env: dict[str, str], embedder):
    """Build the in-process SDK MCP server exposing the hybrid-search tool."""
    dsn = env.get("DATABASE_URI", _DEFAULT_DSN)

    @tool(
        "hybrid_search",
        "Hybrid (full-text + semantic) search over email-body documents. "
        "Returns ranked passages with their ids; cite facts you use as [cite:gN].",
        {"query": str, "limit": int},
    )
    async def hybrid_search_tool(args: dict) -> dict[str, Any]:
        import psycopg

        query = str(args["query"])
        limit = int(args.get("limit", 5))
        with psycopg.connect(dsn, autocommit=True) as conn:
            results = search_documents(conn, query, embedder, limit=limit)
        return _format_content(results)

    return create_sdk_mcp_server("ariadne", tools=[hybrid_search_tool])
