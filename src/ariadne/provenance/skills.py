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
# ToolUseBlock instead. The Skill tool's input schema lives in the CLI (the binary the Python
# SDK shells out to via subprocess), not the SDK; read off the bundled CLI v2.1.169 it is
# `skill: z.string().describe("The name of a skill ...")` + `args: z.string().optional()` — so
# the invoked skill's name is under `skill` (`args` carries arguments, not the name). The
# block's *live* presence in the stream is still only exercised by the deferred ratify spend
# (ADR-0034), but the input key no longer is — it is pinned to the primary source.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

# The tool name the model uses to invoke a skill.
SKILL_TOOL_NAME = "Skill"

# The Skill tool carries the invoked skill's name under `skill` — confirmed against the bundled
# CLI's tool schema (v2.1.169: `skill: z.string()`), the binary the SDK subprocess invokes.
SKILL_NAME_KEY = "skill"


def _bare_name(identifier: str) -> str:
    """The skill's frontmatter ``name``, dropping any ``plugin:`` qualifier (and whitespace).

    A skill staged into a per-arm plugin (``ratify``) is invoked plugin-qualified, but the gate
    matches the bare name — so ``candidate:entity-workup`` must reduce to ``entity-workup``.
    """
    return identifier.rsplit(":", 1)[-1].strip()


def skill_invocations(content: Iterable[Any]) -> set[str]:
    """The bare skill names invoked across one AssistantMessage's content blocks.

    Duck-typed on ``ToolUseBlock``'s ``(name, input)`` shape: a block whose name is the Skill
    tool yields the bare skill name from its ``input["skill"]``; text, thinking, and evidence-tool
    calls are ignored. Malformed Skill blocks (no ``skill`` key, empty/non-string value) are
    skipped, never raised — observation must not break a workup.
    """
    found: set[str] = set()
    for block in content:
        if getattr(block, "name", None) != SKILL_TOOL_NAME:
            continue
        inp = getattr(block, "input", None)
        if not isinstance(inp, dict):
            continue
        value = inp.get(SKILL_NAME_KEY)
        if isinstance(value, str) and value.strip():
            found.add(_bare_name(value))
    return found
