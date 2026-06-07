"""The LLM mapper, made ontology-aware (ADR-0027), hermetic.

When a user ontology is present the model is constrained to *their* vocabulary:
the forced-tool schema carries the declared types as ``enum``s, the prompt
describes the vocabulary, and the repair loop re-prompts on conformance errors as
well as structural ones. The model call stays behind the injected ``call_llm`` seam.
"""

from __future__ import annotations

from ariadne.introspect.postgres import Column, ForeignKey, SchemaSummary
from ariadne.mapping.llm_mapper import (
    build_map_tool,
    build_mapping_prompt,
    propose_with_repair,
)
from ariadne.mapping.ontology import load_ontology_toml
from ariadne.mapping.schema import validate_mapping

_ONTOLOGY = load_ontology_toml(
    """
[[entity_types]]
name = "person"
[[entity_types]]
name = "org"
[[relationship_types]]
name = "MEMBER_OF"
domain = "person"
range = "org"
"""
)


def _summary() -> SchemaSummary:
    return SchemaSummary(
        tables={
            "employees": (
                Column("id", "integer"),
                Column("name", "text"),
                Column("dept_id", "integer"),
            ),
            "departments": (Column("id", "integer"), Column("name", "text")),
        },
        foreign_keys=(ForeignKey("employees", "dept_id", "departments", "id"),),
    )


_CONFORMANT = {
    "entities": [
        {"table": "employees", "type": "person", "id_column": "id", "name_column": "name"},
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
# 'gadget' is not in the ontology -> validate_against_ontology flags it.
_OFF_VOCABULARY = {
    "entities": [
        {"table": "employees", "type": "gadget", "id_column": "id", "name_column": "name"},
        {"table": "departments", "type": "org", "id_column": "id", "name_column": "name"},
    ],
    "relationships": [],
}


class _FakeLLM:
    def __init__(self, *responses: dict) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> dict:
        self.prompts.append(prompt)
        return self._responses[min(len(self.prompts) - 1, len(self._responses) - 1)]


# ── build_map_tool: the forced-tool schema, optionally enum-constrained ──


def _entity_type_field(tool: dict) -> dict:
    return tool["input_schema"]["properties"]["entities"]["items"]["properties"]["type"]


def _relationship_type_field(tool: dict) -> dict:
    return tool["input_schema"]["properties"]["relationships"]["items"]["properties"]["type"]


def test_build_map_tool_without_ontology_leaves_type_an_open_string() -> None:
    tool = build_map_tool(None)
    assert "enum" not in _entity_type_field(tool)
    assert "enum" not in _relationship_type_field(tool)


def test_build_map_tool_with_ontology_constrains_entity_types_to_the_vocabulary() -> None:
    enum = _entity_type_field(build_map_tool(_ONTOLOGY))["enum"]
    assert set(enum) == {"person", "org"}


def test_build_map_tool_with_ontology_constrains_relationship_types_to_the_vocabulary() -> None:
    enum = _relationship_type_field(build_map_tool(_ONTOLOGY))["enum"]
    assert set(enum) == {"MEMBER_OF"}


# ── build_mapping_prompt: describes the vocabulary when an ontology is present ──


def test_prompt_describes_the_ontology_vocabulary() -> None:
    prompt = build_mapping_prompt(_summary(), ontology=_ONTOLOGY)
    assert "person" in prompt and "org" in prompt
    assert "MEMBER_OF" in prompt  # the legal edge, with its routing, is named


# ── propose_with_repair: the loop enforces conformance, not just loadability ──


def test_conformant_first_proposal_returns_immediately() -> None:
    llm = _FakeLLM(_CONFORMANT)
    mapping = propose_with_repair(_summary(), call_llm=llm, ontology=_ONTOLOGY)
    assert validate_mapping(mapping, _summary()) == []
    assert len(llm.prompts) == 1


def test_off_vocabulary_proposal_is_repaired_against_the_ontology() -> None:
    llm = _FakeLLM(_OFF_VOCABULARY, _CONFORMANT)
    mapping = propose_with_repair(_summary(), call_llm=llm, ontology=_ONTOLOGY)
    assert all(e.type in {"person", "org"} for e in mapping.entities)
    assert len(llm.prompts) == 2  # one ontology-driven retry
    assert "gadget" in llm.prompts[1] and "ontology" in llm.prompts[1]


def test_without_ontology_the_loop_ignores_vocabulary() -> None:
    # The same off-vocabulary proposal is fine when no ontology constrains it: a
    # free-string 'gadget' type is structurally loadable, so no retry happens.
    llm = _FakeLLM(_OFF_VOCABULARY)
    mapping = propose_with_repair(_summary(), call_llm=llm)
    assert len(llm.prompts) == 1
    assert any(e.type == "gadget" for e in mapping.entities)
