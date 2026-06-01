# skills/

Agent Skills — packaged, auto-discoverable analytic procedures. **Empty until
Phase 1.**

Each skill is a directory `skills/<name>/SKILL.md` (Markdown + YAML frontmatter:
`name`, `description`, optional `tags`) plus any supporting scripts/templates.
Only metadata is scanned at startup; the body loads when the skill is invoked
(see the [SDK reference](../docs/research/claude-agent-sdk-reference.md), §2).

First planned skill: **`entity-workup`** — given a target entity, run the
minimal retrieve → reason → synthesize loop (graph relationships → structured
facts → unstructured evidence → cited analytic note). Keep skill descriptions
specific so auto-invocation triggers reliably.

> Note: the SDK ignores the `allowed-tools` frontmatter field — tool access is
> controlled by the harness's `allowedTools`, not the skill file.
