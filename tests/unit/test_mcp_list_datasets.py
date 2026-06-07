"""`list_datasets` exposes the workable datasets over MCP (the A3 enumeration foundation).

A host agent calling ``workup(dataset=...)`` needs to know which datasets exist — the
built-ins *and* the user stores ratified under ``$ARIADNE_MAPPINGS`` (ADR-0025). This
mirrors ``list_profiles`` and is the seam dynamic per-dataset tool families (A3) build on.
"""

from __future__ import annotations

from ariadne.mapping.schema import DatasetHeader, EntityMapping, Mapping, dump_mapping_toml
from ariadne.mcp_server import list_datasets_info


def test_lists_builtin_datasets_with_type_and_access() -> None:
    info = list_datasets_info({})
    # the built-in adapters register on import; `synthetic` is workup's default dataset
    assert "synthetic" in info
    assert set(info["synthetic"]) == {"entity_type", "access"}
    assert info["synthetic"]["access"] in {"public", "restricted"}


def test_includes_user_mapped_datasets_from_ariadne_mappings(tmp_path) -> None:
    mapping = Mapping(entities=(EntityMapping("people", "person", "id", "name"),))
    header = DatasetHeader(name="acme_crm", dsn_env="ACME_DSN")
    (tmp_path / "acme.toml").write_text(dump_mapping_toml(mapping, header), encoding="utf-8")

    info = list_datasets_info({"ARIADNE_MAPPINGS": str(tmp_path)})

    assert "acme_crm" in info  # a ratified user mapping is discoverable over MCP
    assert info["acme_crm"]["access"] == "restricted"  # user stores default to restricted


def test_lists_the_multimodal_connector_slate() -> None:
    # the ADR-0018 built-in slate (text / audio / relational) is all discoverable over MCP
    info = list_datasets_info({})
    assert {"enron", "worldspeech", "lahman"} <= set(info)
