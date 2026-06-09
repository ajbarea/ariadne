"""Observe which Agent Skills the model invoked during a workup (ADR-0034).

The SkillTester invocation gate needs to know whether the candidate skill actually fired —
otherwise a measured delta is ambient model variance, not the skill. The obvious channel
(a ``PostToolUse`` hook matching ``Skill``) does **not** work: the Skill tool is handled as
prompt expansion and never reaches the hook pipeline, so the hook never fires
(anthropics/claude-code#43630, closed *not-planned*). The signal is read off the message
stream instead — a skill call surfaces as a ``ToolUseBlock(name="Skill", ...)`` in an
AssistantMessage's content, which ``run_workup`` already iterates. This is the issue's
transcript-parse workaround done inline on the live stream (no lost data, no dependency on
locating a transcript file).

# research(2026-06): hooks do not fire for Skill invocations — prompt-expansion bypasses the
# tool pipeline (anthropics/claude-code#43630, closed not-planned). Read the streamed Skill
# ToolUseBlock instead. The Skill tool's input schema lives in the CLI (not the Python SDK),
# so the exact input key and the block's live presence in the stream are confirmed when the
# live ratify execution runs (the deferred spend step, ADR-0034).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

# The tool name the model uses to invoke a skill.
SKILL_TOOL_NAME = "Skill"

# The Skill tool carries the invoked skill under one of these input keys. `skill` is the shape
# the upstream feature request names (anthropics/claude-code#43630); the others cover the
# slash-command / name-field variants — tolerated until a live run pins the exact key.
_SKILL_INPUT_KEYS = ("skill", "command", "name", "skill_name")


def _bare_name(identifier: str) -> str:
    """The skill's frontmatter ``name``, dropping any ``plugin:`` qualifier (and whitespace).

    A skill staged into a per-arm plugin (``ratify``) is invoked plugin-qualified, but the gate
    matches the bare name — so ``candidate:entity-workup`` must reduce to ``entity-workup``.
    """
    return identifier.rsplit(":", 1)[-1].strip()


def skill_invocations(content: Iterable[Any]) -> set[str]:
    """The bare skill names invoked across one AssistantMessage's content blocks.

    Duck-typed on ``ToolUseBlock``'s ``(name, input)`` shape: a block whose name is the Skill
    tool yields the bare skill name from its input; text, thinking, and evidence-tool calls are
    ignored. Malformed Skill blocks (no recognizable key, empty/non-string value) are skipped,
    never raised — observation must not break a workup.
    """
    found: set[str] = set()
    for block in content:
        if getattr(block, "name", None) != SKILL_TOOL_NAME:
            continue
        inp = getattr(block, "input", None)
        if not isinstance(inp, dict):
            continue
        for key in _SKILL_INPUT_KEYS:
            value = inp.get(key)
            if isinstance(value, str) and value.strip():
                found.add(_bare_name(value))
                break
    return found
