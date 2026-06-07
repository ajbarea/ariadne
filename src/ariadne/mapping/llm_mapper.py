"""LLM-backed ``SchemaMapper`` (ADR-0026, the agentic half of ADR-0020 axis A1).

A real Claude model proposes how a user's introspected schema maps onto the
canonical person/org/site/document schema, via **forced tool-use** (structured
output, not prose to parse — mirrors ``evaluation/judge.py``). A bounded,
validator-terminated retry loop re-prompts with the structural validator's
complaints until the proposal is loadable or the attempt bound is hit (mirrors
``provenance/repair.py``); the deterministic validator is the gate, never the
model's self-judgment.

# research(2026-06): structured output = schema + validator + repair loop (the 2026
# consensus); forced tool-use carries the schema (judge.py pattern). Full AutoLink
# schema-exploration (arXiv:2511.17190) is deferred for large schemas. ADR-0026.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ariadne.mapping.schema import (
    EntityMapping,
    Mapping,
    RelationshipMapping,
    validate_mapping,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from ariadne.introspect.postgres import SchemaSummary

MAX_MAP_ATTEMPTS = 3  # initial proposal + up to two validator-driven retries
_DEFAULT_MODEL = "claude-opus-4-8"

# Forced-tool schema: the model returns the mapping as typed structure, not prose.
MAP_TOOL: dict[str, Any] = {
    "name": "propose_mapping",
    "description": (
        "Submit the mapping of the user's tables onto Ariadne's canonical schema: which "
        "tables are entities, their id/name/attribute columns, and which foreign keys "
        "are relationships."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "table": {"type": "string"},
                        "type": {
                            "type": "string",
                            "description": "canonical entity type, an open string: "
                            "person | org | site | document | unit | topic | ...",
                        },
                        "id_column": {"type": "string"},
                        "name_column": {"type": "string"},
                        "attribute_columns": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["table", "type", "id_column", "name_column"],
                },
            },
            "relationships": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "description": "canonical relationship type, e.g. MEMBER_OF",
                        },
                        "from_table": {"type": "string"},
                        "to_table": {"type": "string"},
                        "from_column": {
                            "type": "string",
                            "description": "the foreign-key column on from_table",
                        },
                        "to_column": {
                            "type": "string",
                            "description": "the referenced column on to_table",
                        },
                    },
                    "required": ["type", "from_table", "to_table", "from_column", "to_column"],
                },
            },
        },
        "required": ["entities"],
    },
}

_SYSTEM = (
    "You map a user's relational schema onto Ariadne's canonical sensemaking schema "
    "(person / org / site / document entities + typed relationships). Each table that "
    "names a real-world entity becomes an entity with an id column and a human-readable "
    "name column; its descriptive columns become attributes; each foreign key linking two "
    "mapped entities becomes a relationship. The canonical type is an open string — pick "
    "the most natural one. Submit the mapping with the propose_mapping tool."
)


def _describe_schema(summary: SchemaSummary) -> str:
    tables = "\n".join(
        f"- {table}: " + ", ".join(f"{c.name} ({c.data_type})" for c in cols)
        for table, cols in summary.tables.items()
    )
    fks = "\n".join(
        f"- {fk.from_table}.{fk.from_column} -> {fk.to_table}.{fk.to_column}"
        for fk in summary.foreign_keys
    )
    return f"## Tables\n{tables}" + (f"\n\n## Foreign keys\n{fks}" if fks else "")


def build_mapping_prompt(summary: SchemaSummary, errors: Sequence[str] = ()) -> str:
    """Render the proposal prompt; on a retry, include the validator's errors to fix."""
    prompt = (
        "Map this introspected Postgres schema onto the canonical person/org/site/document "
        "schema. Use only column names that appear below.\n\n"
        f"{_describe_schema(summary)}"
    )
    if errors:
        listed = "\n".join(f"- {e}" for e in errors)
        prompt += (
            f"\n\n## Fix these problems with your previous proposal\n{listed}\n"
            "Re-submit a corrected mapping with propose_mapping."
        )
    return prompt


def parse_mapping(tool_input: dict[str, Any]) -> Mapping:
    """Convert a ``propose_mapping`` tool input into a ``Mapping`` (raises if malformed)."""
    entities = tuple(
        EntityMapping(
            table=e["table"],
            type=e["type"],
            id_column=e["id_column"],
            name_column=e["name_column"],
            attribute_columns=tuple(e.get("attribute_columns", [])),
        )
        for e in tool_input["entities"]
    )
    relationships = tuple(
        RelationshipMapping(
            type=r["type"],
            from_table=r["from_table"],
            to_table=r["to_table"],
            from_column=r["from_column"],
            to_column=r["to_column"],
        )
        for r in tool_input.get("relationships", [])
    )
    return Mapping(entities=entities, relationships=relationships)


def propose_with_repair(
    summary: SchemaSummary,
    *,
    call_llm: Callable[[str], dict[str, Any]],
    max_attempts: int = MAX_MAP_ATTEMPTS,
) -> Mapping:
    """Propose -> validate -> re-prompt with errors, bounded; the validator terminates.

    Returns the first loadable mapping, or the last parseable draft if the bound is hit
    (the draft is written regardless — ``propose_and_write`` re-validates and a human
    ratifies). A malformed proposal is fed back as an error and retried, too.
    """
    errors: list[str] = []
    mapping: Mapping | None = None
    for _ in range(max_attempts):
        tool_input = call_llm(build_mapping_prompt(summary, errors))
        try:
            mapping = parse_mapping(tool_input)
        except (KeyError, TypeError) as exc:
            errors = [f"malformed proposal, missing/invalid field: {exc}"]
            continue
        errors = validate_mapping(mapping, summary)
        if not errors:
            return mapping
    if mapping is None:
        raise RuntimeError("LLM mapper produced no parseable mapping within the attempt bound")
    return mapping


class ClaudeSchemaMapper:
    """A ``SchemaMapper`` backed by the Claude Messages API. Requires the ``adaptive`` extra.

    Forces the ``propose_mapping`` tool call for structured output, then runs the
    bounded validator-terminated retry loop (``propose_with_repair``). Mirrors
    ``evaluation.judge.ClaudeAnalyticJudge`` — the ``anthropic`` client is lazy-imported
    so the static checker and the core package stay clean without the extra.
    """

    def __init__(
        self,
        *,
        model: str = _DEFAULT_MODEL,
        max_tokens: int = 2048,
        max_attempts: int = MAX_MAP_ATTEMPTS,
    ) -> None:
        import importlib

        anthropic = importlib.import_module("anthropic")
        # `Any`: the client is from the optional `adaptive` extra, so its precise types
        # only exist when installed (the optional-extra trap — same as judge.py).
        self._client: Any = anthropic.Anthropic()
        self._model = model
        self._max_tokens = max_tokens
        self._max_attempts = max_attempts

    def _call_llm(self, prompt: str) -> dict[str, Any]:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=_SYSTEM,
            tools=[MAP_TOOL],
            tool_choice={"type": "tool", "name": "propose_mapping"},
            messages=[{"role": "user", "content": prompt}],
        )
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == "propose_mapping":
                return dict(block.input)
        raise RuntimeError("mapper did not return a propose_mapping tool call")

    def propose(self, summary: SchemaSummary) -> Mapping:
        return propose_with_repair(
            summary, call_llm=self._call_llm, max_attempts=self._max_attempts
        )
