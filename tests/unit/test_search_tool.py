from __future__ import annotations

from ariadne.unstructured.embed import FakeEmbedder
from ariadne.unstructured.search_tool import ARIADNE_TOOLS, _format_content, make_ariadne_server


def test_format_content_wraps_passages_for_the_agent() -> None:
    out = _format_content([{"id": "email:1", "text": "the shipment leaves at dawn"}])
    assert out["content"][0]["type"] == "text"
    assert "email:1" in out["content"][0]["text"] and "shipment" in out["content"][0]["text"]


def test_format_content_handles_no_results() -> None:
    out = _format_content([])
    assert "No matching" in out["content"][0]["text"]


def test_tool_name_constant() -> None:
    assert ARIADNE_TOOLS == ["mcp__ariadne__hybrid_search"]


def test_make_ariadne_server_builds_an_sdk_server() -> None:
    server = make_ariadne_server({"DATABASE_URI": "postgresql://x"}, FakeEmbedder(dim=8))
    assert server is not None  # constructed without touching the DB


def test_search_documents_preserves_rrf_rank_order(monkeypatch) -> None:
    from ariadne.unstructured import search_tool

    # hybrid_search returns RRF order [b, a]; the DB returns rows in a DIFFERENT order.
    monkeypatch.setattr(search_tool, "hybrid_search", lambda conn, q, e, *, limit: ["b", "a"])

    class _Cur:
        def fetchall(self):
            return [("a", "alpha text"), ("b", "beta text")]  # DB order a,b

    class _Conn:
        def execute(self, sql, params):
            return _Cur()

    results = search_tool.search_documents(_Conn(), "q", object(), limit=5)
    assert [r["id"] for r in results] == ["b", "a"]  # RRF order, not DB order
    assert results[0]["text"] == "beta text"


def test_search_documents_empty_when_no_ids(monkeypatch) -> None:
    from ariadne.unstructured import search_tool

    monkeypatch.setattr(search_tool, "hybrid_search", lambda conn, q, e, *, limit: [])
    assert search_tool.search_documents(object(), "q", object()) == []
