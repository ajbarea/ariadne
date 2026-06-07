"""Gated integration test for the real Claude-backed schema mapper (ADR-0026).

Skipped unless `anthropic` (the `adaptive` extra) is installed and ANTHROPIC_API_KEY
is set — it makes real Claude Messages calls (no Docker, hence the `network` marker
so the Docker-down skip does not apply). The hermetic suite uses a fake call_llm.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("anthropic")

from ariadne.introspect.postgres import Column, ForeignKey, SchemaSummary
from ariadne.mapping.llm_mapper import ClaudeSchemaMapper
from ariadne.mapping.schema import validate_mapping

pytestmark = [pytest.mark.integration, pytest.mark.network]


def _summary() -> SchemaSummary:
    # `full_name` (not `name`) and `salary` exercise real judgment: the model must pick
    # the human-readable name column and route the FK to a relationship.
    return SchemaSummary(
        tables={
            "employees": (
                Column("id", "integer"),
                Column("full_name", "text"),
                Column("salary", "integer"),
                Column("dept_id", "integer"),
            ),
            "departments": (Column("id", "integer"), Column("name", "text")),
        },
        foreign_keys=(ForeignKey("employees", "dept_id", "departments", "id"),),
    )


@pytest.fixture(scope="module")
def mapper() -> ClaudeSchemaMapper:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("no ANTHROPIC_API_KEY — live mapper run skipped")
    return ClaudeSchemaMapper()


def test_live_mapper_proposes_a_loadable_mapping(mapper: ClaudeSchemaMapper) -> None:
    summary = _summary()
    mapping = mapper.propose(summary)
    # The validator-terminated loop yields a structurally loadable mapping.
    assert validate_mapping(mapping, summary) == []
    # Both tables became entities and the foreign key became a relationship.
    assert {e.table for e in mapping.entities} == {"employees", "departments"}
    assert any(
        r.from_table == "employees" and r.to_table == "departments" for r in mapping.relationships
    )
    # The model picked the human-readable name column, not the id.
    emp = next(e for e in mapping.entities if e.table == "employees")
    assert emp.name_column == "full_name"
