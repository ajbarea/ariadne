"""Unit tests for ariadne.provenance.skills — observing Skill invocations off the stream.

PostToolUse hooks never fire for Skill (anthropics/claude-code#43630, closed not-planned —
the Skill tool is prompt-expansion and bypasses the tool pipeline), so the invocation signal
the SkillTester gate (ADR-0034) needs is read off the message stream: a skill call surfaces
as a ``ToolUseBlock(name="Skill", ...)`` in an AssistantMessage's content.
"""

from __future__ import annotations

from claude_agent_sdk import TextBlock, ToolUseBlock

from ariadne.provenance.skills import SKILL_TOOL_NAME, skill_invocations


def test_extracts_bare_skill_name_from_skill_tool_use() -> None:
    blocks = [ToolUseBlock(id="t1", name=SKILL_TOOL_NAME, input={"skill": "entity-workup"})]
    assert skill_invocations(blocks) == {"entity-workup"}


def test_strips_plugin_qualifier_to_bare_name() -> None:
    # A staged-plugin skill is invoked plugin-qualified, but the gate matches the bare
    # `name:` frontmatter — so a `candidate:entity-workup` invocation must read as `entity-workup`.
    blocks = [ToolUseBlock(id="t1", name="Skill", input={"skill": "candidate:entity-workup"})]
    assert skill_invocations(blocks) == {"entity-workup"}


def test_tolerates_alternate_input_key() -> None:
    # The Skill tool's input schema lives in the CLI, not the Python SDK; the exact key is
    # validated at live-execution time, so the extractor accepts the plausible shapes.
    blocks = [ToolUseBlock(id="t1", name="Skill", input={"command": "closing-citation-audit"})]
    assert skill_invocations(blocks) == {"closing-citation-audit"}


def test_ignores_evidence_tool_calls() -> None:
    blocks = [
        ToolUseBlock(id="t1", name="mcp__neo4j__read_neo4j_cypher", input={"query": "MATCH (n)"}),
        ToolUseBlock(id="t2", name="mcp__postgres__execute_sql", input={"sql": "SELECT 1"}),
    ]
    assert skill_invocations(blocks) == set()


def test_picks_only_the_skill_out_of_a_mixed_content_list() -> None:
    blocks = [
        TextBlock(text="Let me run the entity workup."),
        ToolUseBlock(id="t1", name="Skill", input={"skill": "entity-workup"}),
        ToolUseBlock(id="t2", name="mcp__neo4j__get_neo4j_schema", input={}),
    ]
    assert skill_invocations(blocks) == {"entity-workup"}


def test_unions_multiple_skill_calls() -> None:
    blocks = [
        ToolUseBlock(id="t1", name="Skill", input={"skill": "entity-workup"}),
        ToolUseBlock(id="t2", name="Skill", input={"skill": "aux:enumeration-query"}),
    ]
    assert skill_invocations(blocks) == {"entity-workup", "enumeration-query"}


def test_whitespace_in_identifier_is_trimmed() -> None:
    blocks = [ToolUseBlock(id="t1", name="Skill", input={"skill": "  candidate:entity-workup  "})]
    assert skill_invocations(blocks) == {"entity-workup"}


def test_malformed_skill_blocks_are_skipped_not_raised() -> None:
    blocks = [
        ToolUseBlock(id="t1", name="Skill", input={}),  # no recognizable key
        ToolUseBlock(id="t2", name="Skill", input={"skill": ""}),  # empty value
        ToolUseBlock(id="t3", name="Skill", input={"skill": 7}),  # non-string value
    ]
    assert skill_invocations(blocks) == set()


def test_empty_content_yields_empty_set() -> None:
    assert skill_invocations([]) == set()
