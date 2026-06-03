# 0009 — Distribute Ariadne as an MCP server, wrapped in a Claude Code plugin

- **Status:** Accepted (2026-06-03)
- **Deciders:** Ariadne maintainers
- **Relates to:** [ADR-0001](0001-orchestration-on-claude-agent-sdk.md) (Ariadne is an Agent SDK *application*)

## Context

We want Ariadne's sensemaking usable from **any AI CLI** (Claude Code, Copilot,
Gemini CLI, Cursor, a fresh machine) — installable like a marketplace plugin and
callable from anywhere, not just from the local `ariadne` CLI. The reference
point is the in-house **techne** Claude Code plugin.

The constraint that shapes the answer: Ariadne is an **Agent SDK application** —
it runs its *own* gather→act→verify→synthesize loop with code-level rigor
(provenance hook, citation gate, tradecraft lint, eval). It is not a set of
dev-workflow skills like techne. So "make it a plugin" must not dissolve the
harness.

## Decision drivers

- **Cross-CLI portability** — one artifact usable by every MCP-speaking client,
  not a Claude-Code-only package.
- **One-click install + slash UX** for the clients that support it.
- **Preserve the harness/rigor** — the loop and gates stay intact.
- **Reuse what exists** — `run_workup`, the connectors, the hybrid-search tool.

## Considered options

### A. Claude Code plugin only (skills + hooks, like techne)

- **Pros:** one-click install + `/ariadne:workup` in Claude Code; matches the
  techne convention.
- **Cons:** Claude-Code-specific — does **not** reach Gemini CLI / Cursor /
  generic MCP clients; and a skills-only package can't carry Ariadne's
  application loop + tested gates (those aren't markdown instructions).

### B. MCP server only (FastMCP, PyPI/`uvx`)

- **Pros:** **universal** — every MCP client (Claude, Copilot, Gemini, Cursor,
  Windsurf, ChatGPT) adds it with identical config; the MCP registry is the
  cross-CLI "marketplace"; the server wraps the harness so rigor is preserved.
- **Cons:** no one-click Claude Code install or slash-command UX on its own.

### C. MCP server as the engine + a Claude Code plugin that bundles it (chosen)

- **Pros:** the **MCP server is the universal layer** (works in any CLI), and the
  **plugin is the convenience wrapper** for Claude Code / Copilot — bundling the
  server's `.mcp.json` + Ariadne skills so one install wires both. Best of both.
- **Cons:** two surfaces to maintain (mitigated: the plugin is thin; both wrap
  the same code).

## Decision

**Adopt C.** Two layers over the existing harness:

1. **The engine — an `ariadne` MCP server** (FastMCP; stdio for local, HTTP for
   shared). It exposes a headline tool `workup(entity, dataset)` that runs the
   existing `run_workup` harness *internally* and returns the cited analytic note,
   plus optional lower-level retrieval tools (`hybrid_search`, graph query) for
   composition. The host agent delegates "do a rigorous entity workup" to Ariadne
   as a black-box specialist; the rigor (provenance/citation/eval) stays inside.
   Distributed via **PyPI → `uvx`** and listed in the **MCP registry**.
2. **The wrapper — a Claude Code plugin** mirroring techne's convention: the repo
   doubles as a marketplace (`.claude-plugin/marketplace.json` at root) with
   `plugins/ariadne/` carrying `plugin.json`, a bundled **`.mcp.json`** (pointing
   at the MCP server), and Ariadne **skills** (e.g. an analyst-workup skill that
   routes to the `workup` tool). One install in Claude Code / Copilot wires the
   skill + the MCP server together with a `/ariadne:workup` slash interface.

The MCP server is the source of truth for "use it anywhere"; the plugin is a
Claude-Code-flavoured convenience built on top. The plugin does **not** fold into
techne (different audience: analysts vs. developers).

## Consequences

- Any MCP-speaking CLI on any machine can add the server (identical config JSON)
  and call `ariadne_workup` — true "from anywhere."
- Claude Code / Copilot users get one-click install + slash UX via the plugin.
- The harness and its tested gates are preserved (the server runs the loop).
- The ariadne repo gains a marketplace + plugin surface alongside the app — built
  server-first, plugin second.
- **Config caveat:** the *tool* is portable; the *data* is not. Each install
  points the server at its stores (Neo4j / Postgres) + an API key, per the normal
  MCP model (cf. the Postgres / Firebase MCP servers).

## Sources

- MCP cross-client ubiquity & identical config across Claude / Copilot / Cursor /
  Gemini; the MCP registry as the cross-CLI marketplace (2,000+ servers, Q1 2026).
- [FastMCP](https://gofastmcp.com/) — Python MCP servers; `uvx`/PyPI distribution.
- [Claude Code plugins reference](https://code.claude.com/docs/en/plugins-reference) — `.claude-plugin/`, `.mcp.json`, `skills/`.
- In-house convention: `techne` (`ajbarea/techne`) — repo-as-marketplace + `plugins/<name>/`.
