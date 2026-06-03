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
