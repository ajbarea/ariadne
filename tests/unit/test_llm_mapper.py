"""LLM schema mapper (ADR-0026), hermetic: pure prompt/parse + the retry loop.

The real ``anthropic`` path lives in ``ClaudeSchemaMapper`` (live-gated test);
here the loop runs over an injected fake ``call_llm`` so no key/network is needed.
"""

from __future__ import annotations

import pytest

from ariadne.introspect.postgres import Column, ForeignKey, SchemaSummary
from ariadne.mapping.llm_mapper import (
    build_mapping_prompt,
    parse_mapping,
    propose_with_repair,
)
from ariadne.mapping.schema import Mapping, validate_mapping


def _summary() -> SchemaSummary:
    return SchemaSummary(
        tables={
            "employees": (
                Column("id", "integer"),
                Column("name", "text"),
                Column("salary", "integer"),
                Column("dept_id", "integer"),
            ),
            "departments": (Column("id", "integer"), Column("name", "text")),
        },
        foreign_keys=(ForeignKey("employees", "dept_id", "departments", "id"),),
    )


_VALID = {
    "entities": [
        {
            "table": "employees",
            "type": "person",
            "id_column": "id",
            "name_column": "name",
            "attribute_columns": ["salary"],
        },
        {"table": "departments", "type": "org", "id_column": "id", "name_column": "name"},
    ],
    "relationships": [
        {
            "type": "MEMBER_OF",
            "from_table": "employees",
            "to_table": "departments",
            "from_column": "dept_id",
            "to_column": "id",
        }
    ],
}
# id_column 'ghost' is not in the schema -> validate_mapping flags it (unloadable).
_INVALID = {
    "entities": [
        {"table": "employees", "type": "person", "id_column": "ghost", "name_column": "name"}
    ],
    "relationships": [],
}
# missing the required id_column key -> parse_mapping raises.
_MALFORMED = {
    "entities": [{"table": "employees", "type": "person", "name_column": "name"}],
    "relationships": [],
}


class _FakeLLM:
    """Serves queued tool-input dicts and records the prompts it was called with."""

    def __init__(self, *responses: dict) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> dict:
        self.prompts.append(prompt)
        return self._responses[min(len(self.prompts) - 1, len(self._responses) - 1)]


# ── build_mapping_prompt: pure render of the schema + canonical target + retry errors ──


def test_build_mapping_prompt_describes_the_schema() -> None:
    prompt = build_mapping_prompt(_summary())
    assert "employees" in prompt and "dept_id" in prompt
    assert "departments" in prompt
    # names the canonical target so the model maps INTO it, not to a free ontology
    assert "person" in prompt or "canonical" in prompt


def test_build_mapping_prompt_surfaces_validation_errors_on_retry() -> None:
    errors = ["column employees.'ghost' is not in the schema"]
    prompt = build_mapping_prompt(_summary(), errors)
    assert "ghost" in prompt  # the model is told exactly what to fix


# ── parse_mapping: tool_input dict -> Mapping ──


def test_parse_mapping_builds_entities_and_relationships() -> None:
    mapping = parse_mapping(_VALID)
    assert isinstance(mapping, Mapping)
    assert {e.table for e in mapping.entities} == {"employees", "departments"}
    emp = next(e for e in mapping.entities if e.table == "employees")
    assert emp.type == "person" and emp.attribute_columns == ("salary",)
    assert mapping.relationships[0].type == "MEMBER_OF"


def test_parse_mapping_defaults_missing_attribute_columns_to_empty() -> None:
    dept = next(e for e in parse_mapping(_VALID).entities if e.table == "departments")
    assert dept.attribute_columns == ()


def test_parse_mapping_raises_on_a_missing_required_key() -> None:
    with pytest.raises((KeyError, TypeError)):
        parse_mapping(_MALFORMED)


# ── propose_with_repair: bounded, validator-terminated retry over injected call_llm ──


def test_propose_with_repair_returns_a_valid_first_proposal() -> None:
    llm = _FakeLLM(_VALID)
    mapping = propose_with_repair(_summary(), call_llm=llm, max_attempts=3)
    assert validate_mapping(mapping, _summary()) == []
    assert len(llm.prompts) == 1  # no retry needed


def test_propose_with_repair_retries_on_validation_error_then_succeeds() -> None:
    llm = _FakeLLM(_INVALID, _VALID)
    mapping = propose_with_repair(_summary(), call_llm=llm, max_attempts=3)
    assert validate_mapping(mapping, _summary()) == []
    assert len(llm.prompts) == 2  # one retry
    assert "ghost" in llm.prompts[1]  # the retry prompt carries the validator's complaint


def test_propose_with_repair_recovers_from_a_malformed_proposal() -> None:
    llm = _FakeLLM(_MALFORMED, _VALID)
    mapping = propose_with_repair(_summary(), call_llm=llm, max_attempts=3)
    assert validate_mapping(mapping, _summary()) == []
    assert len(llm.prompts) == 2


def test_propose_with_repair_is_bounded_and_returns_best_effort() -> None:
    # The model never fixes the error; the loop stops at max_attempts and returns the
    # last parseable draft (propose_and_write re-validates + a human ratifies).
    llm = _FakeLLM(_INVALID)
    mapping = propose_with_repair(_summary(), call_llm=llm, max_attempts=2)
    assert isinstance(mapping, Mapping)
    assert len(llm.prompts) == 2  # exactly the bound, no infinite loop
