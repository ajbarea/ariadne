# skills/

Agent Skills are packaged, auto-discoverable analytic procedures. The shipped skills live in
[`.claude/skills/entity-workup/`](../.claude/skills/entity-workup/) (the procedure the CLI
agent loop follows) and [`plugins/ariadne/skills/analyst-workup/`](../plugins/ariadne/skills/analyst-workup/)
(the thin tool-invoker the Claude Code plugin bundles). This note documents the format.

Each skill is a directory `skills/<name>/SKILL.md` (Markdown + YAML frontmatter:
`name`, `description`, optional `tags`) plus any supporting scripts/templates.
Only metadata is scanned at startup; the body loads when the skill is invoked
(see the [SDK reference](../docs/research/claude-agent-sdk-reference.md), §2).

The shipped `entity-workup` skill: given a target entity, run the gather → act → verify →
synthesize loop (graph relationships → structured facts → unstructured evidence → cited
analytic note). Keep skill descriptions specific so auto-invocation triggers reliably.

> Note: the SDK ignores the `allowed-tools` frontmatter field — tool access is
> controlled by the harness's `allowedTools`, not the skill file.
