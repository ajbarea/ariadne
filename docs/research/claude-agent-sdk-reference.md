# Claude Agent SDK, Primitives Reference (mid-2026)

> **Source:** captured 2026-06-01 from a `claude-code-guide` research agent that
> searched the official Anthropic / Claude Agent SDK docs. Doc-cited. Treat as a
> design reference for Ariadne's harness layer; verify any feature flagged
> *beta* against the live docs before depending on it.

This reference is organized by seven architecture domains: tools, skills, hooks,
subagents, MCP integration, context management, and deployment. Each section has
mechanics, "use it when / don't", gotchas, and official doc URLs.

---

## 1. Tools

Callable functions the agent uses to touch filesystems, run commands, search the
web, etc. ~15 built-ins (`Read`, `Write`, `Edit`, `Bash`, `Glob`, `Grep`,
`WebSearch`, `WebFetch`, `AskUserQuestion`, …); custom tools arrive via MCP
servers or in-process SDK definitions.

- **Tool-use loop:** Claude emits a `tool_use` block → SDK executes → result
  returns → Claude decides next action. Multiple tools from one turn run
  concurrently.
- **In-process (SDK custom tools):** Python functions / TS classes in your app.
  Fastest, direct runtime-state access. Use for app-specific logic.
- **MCP (local stdio):** subprocesses; reusable, language-agnostic packages.
- **MCP (HTTP/SSE):** remote services; credentials via headers/env.
- **Permissions/tokens:** every call is permission-gated (`allowedTools`,
  `permissionMode`). Tool defs cost context tokens, use **tool search** to load
  only needed tools per turn. MCP tools are named `mcp__<server>__<action>`;
  permit families with `allowedTools: ["mcp__db__*"]`.

**Gotchas:** `permissionMode: "acceptEdits"` does **not** auto-approve MCP
tools, use an `allowedTools` wildcard. Tool search can withhold large defs
Claude might have used. Check the `system:init` message for MCP connection
status before running.

Docs: [overview/tools](https://code.claude.com/docs/en/agent-sdk/overview#capabilities)
· [MCP](https://code.claude.com/docs/en/agent-sdk/mcp)
· [custom tools](https://code.claude.com/docs/en/agent-sdk/custom-tools)
· [permissions](https://code.claude.com/docs/en/agent-sdk/permissions)

---

## 2. Skills

Pre-packaged, auto-discoverable capabilities: Markdown + YAML frontmatter on
disk, loaded by description. Skills encapsulate multi-step workflows and domain
knowledge; tools are single callable functions.

- **Location:** `.claude/skills/<name>/SKILL.md` (project) or `~/.claude/...` (user).
- **Frontmatter:** `name`, `description`, optional `tags`. (`allowed-tools` is
  **ignored by the SDK**: control access via the SDK's `allowedTools`.)
- **Progressive disclosure:** only metadata is scanned at startup; full body
  loads when invoked (auto by description match, or `/skill-name`).
- **Multi-file:** a skill dir can carry scripts, templates, data, all available
  when it runs; skills can shell out to Bash and parse outputs.

**Packaging an `entity-workup` skill:** `SKILL.md` with a specific description
(graph relationships → SQL facts → vector evidence → synthesize with citations),
step-by-step body, example invocation, fallbacks, plus supporting scripts/report
templates in the dir. Claude auto-invokes on "run entity workup on …".

**Gotchas:** vague descriptions won't auto-trigger. SDK ignores `allowed-tools`
frontmatter.

Docs: [skills in the SDK](https://code.claude.com/docs/en/agent-sdk/skills)
· [skills overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
· [best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)

---

## 3. Hooks

Callbacks intercepting lifecycle events: block, modify inputs/outputs, inject
context, enforce governance, without hardcoding into prompts.

**Events:** `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `PostToolBatch`
(TS), `UserPromptSubmit`, `MessageDisplay` (TS), `Stop`, `SubagentStart`,
`SubagentStop`, `PreCompact`, `PermissionRequest`, `SessionStart`/`SessionEnd`
(TS), `Notification`. (Python lacks some TS-only events.)

**Can:** block (`permissionDecision: "deny"`), rewrite args (`updatedInput`),
replace/augment results (`updatedToolOutput`), inject context
(`additionalContext`), audit (side effects), defer for human approval, run async
side effects.

**Governance/provenance patterns (directly relevant to Ariadne):**
1. `PostToolUse` audit trail, log every call (timestamp, args, result, user).
2. `PreToolUse` authorization, is this user allowed to query this source?
3. `PostToolUse` redaction, strip PII before Claude sees results.
4. `PostToolUse` **provenance**: record which tool sourced each fact so the
   synthesis cites sources.
5. `PreToolUse` forbidden-pattern blocks (e.g. mutate `.env` / sensitive tables).

**Gotchas:** hooks on one event run **in parallel**: no ordering. Priority:
deny > defer > ask > allow. Matchers filter by **tool name** only, filter by
path inside the callback. Default 60s timeout. `systemMessage` is user-only;
use `additionalContext` to inject info Claude sees.

Docs: [hooks](https://code.claude.com/docs/en/agent-sdk/hooks)
· [hooks reference](https://code.claude.com/docs/en/hooks)

---

## 4. Subagents

Separate specialized agent instances, each with its own fresh context window,
system prompt, and (optional) tool subset.

- **Context isolation:** a subagent gets only its `prompt`, the task description
  passed in, its own tools, and project CLAUDE.md (if `settingSources` includes
  `"project"`). It does **not** see parent history, parent system prompt, or
  preloaded skills (unless listed). **Thread all needed context into the task.**
- **Parallel:** spawn many in one turn; results return as Agent tool outputs.
  Reduces wall-clock but multiplies concurrent API calls (cost/rate limits).
- **Use for:** independent parallel retrieval (e.g. one subagent per data
  source), tool-restricted roles, isolating a long parent conversation.

**Gotchas:** **no nesting**: subagents can't spawn subagents. They don't
inherit parent permissions (set `tools` in the definition). For 100+ fanouts use
dynamic workflows instead.

Docs: [subagents](https://code.claude.com/docs/en/agent-sdk/subagents)
· [workflows](https://code.claude.com/docs/en/agent-sdk/workflows)

---

## 5. MCP integration

The SDK reads `mcpServers` (TS) / `mcp_servers` (Python), or `.mcp.json`, and
discovers tools at startup. Transports: **local stdio** (subprocess; filesystem,
DBs), **HTTP/SSE** (remote; headers for auth), **in-process SDK tools** (no
subprocess).

**Heterogeneous-store connectors (the Ariadne core):**
- **Graph (Neo4j):** stdio server with `NEO4J_URI/USER/PASSWORD` env →
  `mcp__neo4j__query`, `mcp__neo4j__get_schema`, …
- **SQL (Postgres):** stdio server with `DATABASE_URL` → `mcp__postgres__query`,
  `mcp__postgres__list_tables`, …
- **Vector (e.g. Pinecone):** HTTP server with bearer auth → `mcp__pinecone__search`, …

**Auth:** env vars (stdio) or headers (HTTP). SDK doesn't run OAuth flows,
complete OAuth in-app and pass the token. **Permissions:** grant with regex,
e.g. `allowedTools: ["mcp__neo4j__*"]`.

**Gotchas:** server discovery is at startup, new servers need a restart. Large
tool defs → use tool search. Crashes aren't auto-retried; the agent sees the
failure. `acceptEdits` does not auto-approve MCP tools.

Docs: [MCP](https://code.claude.com/docs/en/agent-sdk/mcp)
· [server directory](https://github.com/modelcontextprotocol/servers)
· [custom tools](https://code.claude.com/docs/en/agent-sdk/custom-tools)

---

## 6. Context management

For long multi-hop investigations:

- **Server-side compaction (beta):** auto-summarizes old turns past a token
  threshold (default ~150K). Requires beta header (`compact-2026-01-12`),
  supported on Opus 4.6+ / Sonnet 4.6+. Configurable trigger / instructions.
- **Memory:** `CLAUDE.md` (human-written, loaded every session) + auto-memory
  (machine-written, `~/.claude/projects/<project>/memory/MEMORY.md`, first ~200
  lines loaded at startup). Subagents can keep separate auto-memory.
- **Session storage:** `SessionStore` adapter persists transcripts to S3 / Redis /
  Postgres / custom, required for multi-host resume. Reference impls exist.

**Pattern for long work:** compaction (summarize) + memory (persist critical
facts so they survive compaction) + session storage (durable resume) + subagents
(parallelize to avoid bloating main context). Archive full transcripts via a
`PreCompact` hook if an audit trail is required.

**Gotchas:** compaction is beta. After compaction only root CLAUDE.md
re-injects. SessionStore mirrors transcripts only, generated reports need
separate storage.

Docs: [compaction](https://platform.claude.com/docs/en/build-with-claude/compaction)
· [memory](https://code.claude.com/docs/en/memory)
· [session storage](https://code.claude.com/docs/en/agent-sdk/session-storage)

---

## 7. Deployment

**Requires:** Python 3.10+ or Node 18+; the SDK package (bundles a pinned
`claude` binary); outbound HTTPS to the model endpoint. Spawns a `claude`
subprocess per session. Baseline ~1 GiB RAM / 5 GiB disk / 1 CPU per session.

**Session patterns:** ephemeral (one container per task), long-running
(persistent host, many sessions), hybrid (ephemeral + `SessionStore` hydrate).

**Model routing (env-var switches):** first-party `ANTHROPIC_API_KEY`;
`CLAUDE_CODE_USE_BEDROCK=1`; `CLAUDE_CODE_USE_VERTEX=1`;
`CLAUDE_CODE_USE_FOUNDRY=1` (each + that cloud's creds).

**On-prem / air-gapped, the fork that matters for Ariadne:**
1. **Managed Agents self-hosted sandboxes (beta):** orchestration stays
   Anthropic-side; tool execution moves to your infra via a sandbox-client REST
   API. Data stays in-network.
2. **Agent SDK + egress proxy:** run the SDK in private infra; route all model
   calls through a proxy that enforces domain allowlists, injects credentials,
   and logs for audit.
3. **Open-weight proxy (e.g. gateway vendors):** route Claude-style calls to
   non-Anthropic models, but expect **feature gaps** (hooks/tools/thinking
   parity not guaranteed); test thoroughly.

**Feature availability by environment:** skills/MCP/hooks all work on first-party,
Bedrock, Vertex, Foundry, and self-hosted SDK (with proxy). Air-gapped Managed
Agents: stdio MCP is local-only, HTTP MCP via tunnel (preview). Open-weight
proxy: hooks may differ if the proxy doesn't fully emulate the agent loop.

**Observability:** OTEL traces/metrics/logs via `CLAUDE_CODE_ENABLE_TELEMETRY=1`
(+ OTLP exporter env). Prompt text / tool inputs excluded by default.

Docs: [hosting](https://code.claude.com/docs/en/agent-sdk/hosting)
· [secure deployment](https://code.claude.com/docs/en/agent-sdk/secure-deployment)
· [self-hosted sandboxes](https://platform.claude.com/docs/en/managed-agents/self-hosted-sandboxes)
· [observability](https://code.claude.com/docs/en/agent-sdk/observability)

---

## Unsettled / beta as of mid-2026

Compaction (beta), tool-search withholding behavior, MCP tunnels for air-gapped
Managed Agents (preview), non-deterministic parallel hook order, subagent
resumption after a definition change, SessionStore maturity on Bedrock/Vertex,
and auto-memory in subagents. Verify each against live docs before depending on it.

---

## Implications for Ariadne

1. **Connectors** → graph (Neo4j), SQL (Postgres), vector store as MCP tool
   families; let the agent read schema and write queries; gate with `allowedTools`.
2. **`entity-workup` skill** orchestrates the retrieve → reason → synthesize loop.
3. **Hooks** = provenance (`PostToolUse`, which tool sourced each fact) +
   authorization (`PreToolUse`, may this user query this source?) + a `PreCompact`
   archival hook for the audit trail.
4. **Subagents** fan out parallel per-source retrieval; main agent synthesizes.
5. **Context** = compaction + memory + (for multi-host) `SessionStore`.
6. **Deployment fork** = first-party/cloud now; for air-gap, Managed Agents
   self-hosted sandboxes or SDK-behind-egress-proxy; open-weight only with
   eyes-open feature-gap testing.
