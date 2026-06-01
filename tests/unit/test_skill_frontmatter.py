from __future__ import annotations

from pathlib import Path

SKILL = Path(".claude/skills/entity-workup/SKILL.md")
TEMPLATE = Path(".claude/skills/entity-workup/note-template.md")


def _frontmatter(text: str) -> dict[str, str]:
    assert text.startswith("---\n"), "missing YAML frontmatter"
    _, fm, _ = text.split("---\n", 2)
    out: dict[str, str] = {}
    for line in fm.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            out[key.strip()] = val.strip()
    return out


def test_skill_has_required_frontmatter() -> None:
    fm = _frontmatter(SKILL.read_text(encoding="utf-8"))
    assert fm["name"] == "entity-workup"
    assert "entity" in fm["description"].lower()
    assert len(fm["description"]) > 30  # specific enough to auto-trigger


def test_skill_documents_the_four_phases_and_citation_rule() -> None:
    body = SKILL.read_text(encoding="utf-8").lower()
    for phase in ("gather", "act", "verify", "synthesize"):
        assert phase in body
    assert "[cite:" in SKILL.read_text(encoding="utf-8")


def test_note_template_exists_and_has_sections() -> None:
    body = TEMPLATE.read_text(encoding="utf-8").lower()
    assert "summary" in body
    assert "provenance" in body or "citation" in body
