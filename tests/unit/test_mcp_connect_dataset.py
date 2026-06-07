"""`connect_dataset` activates a ratified dataset at runtime + exposes `workup_<name>` (ADR-0028).

The hermetic core ``activate_dataset`` resolves a ratified mapping under
``$ARIADNE_MAPPINGS`` and registers a per-dataset tool via an injected ``add_tool``; the
``@mcp.tool()`` wraps it with the real FastMCP registration + the ``list_changed`` notify.
Governance: only an already-ratified mapping can be activated — never a raw DSN.
"""

from __future__ import annotations

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from ariadne.mapping.schema import DatasetHeader, EntityMapping, Mapping, dump_mapping_toml
from ariadne.mcp_server import activate_dataset


def _ratify_acme(tmp_path) -> dict[str, str]:
    mapping = Mapping(entities=(EntityMapping("people", "person", "id", "name"),))
    header = DatasetHeader(name="acme", dsn_env="ACME_DSN")
    (tmp_path / "acme.toml").write_text(dump_mapping_toml(mapping, header), encoding="utf-8")
    return {"ARIADNE_MAPPINGS": str(tmp_path)}


def test_activate_registers_a_per_dataset_workup_tool(tmp_path) -> None:
    env = _ratify_acme(tmp_path)
    added: list[str] = []

    def _add(name: str) -> str:
        added.append(name)
        return f"workup_{name}"

    tool_name = activate_dataset("acme", env, add_tool=_add)

    assert tool_name == "workup_acme"
    assert added == ["acme"]  # the ratified dataset's tool was registered


def test_activate_rejects_an_unratified_dataset(tmp_path) -> None:
    # Governance: a name with no ratified mapping under $ARIADNE_MAPPINGS cannot be
    # activated — the agent never onboards unvetted data (ADR-0020 hard boundary).
    env = _ratify_acme(tmp_path)
    with pytest.raises(ValueError, match=r"not an available dataset|ratify"):
        activate_dataset("ghost", env, add_tool=lambda name: f"workup_{name}")


async def test_connect_dataset_exposes_the_tool_over_the_protocol(tmp_path, monkeypatch) -> None:
    # End-to-end over the real MCP protocol (in-memory transport): the dynamically
    # registered workup_<name> tool becomes visible in tools/list after connect_dataset.
    monkeypatch.setenv("ARIADNE_MAPPINGS", _ratify_acme(tmp_path)["ARIADNE_MAPPINGS"])
    from ariadne.mcp_server import mcp

    async with create_connected_server_and_client_session(mcp) as client:
        before = {t.name for t in (await client.list_tools()).tools}
        assert "connect_dataset" in before  # the activation tool ships from the start
        assert "workup_acme" not in before

        await client.call_tool("connect_dataset", {"name": "acme"})

        after = {t.name for t in (await client.list_tools()).tools}
        assert "workup_acme" in after  # the per-dataset tool appeared at runtime
