# 0028, Runtime dataset activation over MCP — `connect_dataset` + a dynamically-registered tool

- **Status:** Accepted (2026-06-07)
- **Deciders:** Ariadne maintainers
- **Refines:** [ADR-0020](0020-adaptive-self-improving-ariadne.md) (axis A3, the dynamic MCP surface) · builds on [ADR-0025](0025-applying-a-ratified-mapping.md) (ratified mappings) + ADR-0009 (Ariadne as an MCP server)

## Context

A3 is the dynamic MCP surface: per-source tool families that appear *at runtime as
datasets connect*, not just whatever was wired at server startup. The enumeration
half shipped (`list_datasets`). This is the activation half: a host agent should be
able to **onboard a user's store mid-session** — point Ariadne at a newly-ratified
mapping and immediately work it up — without restarting the MCP server. MCP's
mechanism is the `tools` `listChanged` capability plus a
`notifications/tools/list_changed` message that tells the client to re-fetch
`tools/list`. The contestable questions: *what* may be activated at runtime (a
governance question), and *how* the notification actually fires on our stack. Hence
this ADR.

## Decision drivers

- **Runtime onboarding without restart is the validated 2026 pattern.** Database-MCP
  practice converged on "dynamic onboarding of new data sources without restart or
  redeployment" — the agent discovers and uses a source mid-session.
- **The propose → ratify → freeze governance spine must hold.** [ADR-0020](0020-adaptive-self-improving-ariadne.md)'s
  hard boundary: the agent operates only on **ratified** artifacts; it never onboards
  data a human hasn't vetted. So runtime *activation* of an already-ratified mapping is
  in bounds; runtime *introspect-map-apply of a raw DSN* is not.
- **The official MCP SDK does not auto-notify.** Ariadne uses the official SDK's bundled
  `mcp.server.fastmcp.FastMCP`, whose `add_tool` only mutates the tool registry — it does
  **not** emit `list_changed` (that auto-notify behaviour belongs to the *separate*
  `jlowin/fastmcp` v2 package). The notification must be sent **manually**, via the
  request's session, and the SDK only delivers it from **within an active request
  context** (registration at server-init fires nothing).
- **A `list_changed` with nothing to list is noise.** The notification signals a *tool*
  set change, so activation has to register an actual tool, not merely an adapter.
- **Hermetically verifiable.** The SDK ships an in-memory client↔server harness, so the
  real protocol path (activate → the new tool is visible via `tools/list`) is testable
  without a network or a second process.

## Considered options

1. **`connect_dataset(dsn=...)` that introspects, maps, and activates a raw store at
   runtime.** *Rejected.* It lets an agent self-onboard unvetted data and skip human
   ratification — a direct breach of [ADR-0020](0020-adaptive-self-improving-ariadne.md)'s
   hard boundary. The mapping must be human-ratified first; the agent only *activates* it.
2. **Register every dataset's tool family statically at server startup.** *Rejected.* No
   runtime onboarding (the whole point of A3), and a startup-registered `workup_<name>`
   is pure redundancy with the existing `workup(dataset=…)` parameter.
3. **Activate the adapter but fire `list_changed` without adding a tool.** *Rejected.*
   `list_changed` is a *tools* signal; with no tool added there is nothing for a client to
   re-discover, and the agent gains no new, selectable capability.
4. **`connect_dataset(name)` activates an already-ratified mapping at runtime: register
   the adapter, expose an intent-named `workup_<name>` tool, and manually send
   `send_tool_list_changed`.** *Chosen.*

## Decision

Adopt **option 4**, in `mcp_server.py`.

- **`connect_dataset(name, ctx)`** resolves `name` to a ratified `*.toml` under
  `$ARIADNE_MAPPINGS` (the same store ADR-0025's `discover_and_register` reads). Not
  found ⇒ a clear error naming the available mappings. Found ⇒ register its
  `MappingDrivenAdapter` (so `workup` can run it) **and** register a per-dataset tool.
- **The per-dataset tool is `workup_<name>(entity, …)`** — a thin wrapper over
  `run_workup_tool(entity, dataset=name, …)`. It is intent-named on purpose: 2026
  tool-design guidance is that names tied to a concrete intent *improve* an agent's
  selection accuracy, and it is the artifact whose appearance `list_changed` announces.
  We accept that it overlaps `workup(dataset=<name>)`; the value is the *runtime
  appearance* and the *named affordance*, not a new capability.
- **The notification is sent manually**, `await ctx.session.send_tool_list_changed()`,
  after `ctx.fastmcp.add_tool(...)`, inside the `connect_dataset` request context — the
  only place the official SDK will actually deliver it. The `tools.listChanged`
  capability is advertised so conforming clients listen.
- **Testable core + DI.** A pure `activate_dataset(name, env, *, register, add_tool)`
  holds the resolve-register-expose logic over injected seams (hermetic unit test); the
  `@mcp.tool()` wires the real FastMCP `add_tool` + the session notification. An
  **in-memory-client integration test** drives the real protocol: list tools (no
  `workup_<name>`), call `connect_dataset`, list tools again (`workup_<name>` present).

## Consequences

- A host agent can onboard a ratified user store **mid-session** — `connect_dataset` then
  `workup_<name>` (or `workup(dataset=<name>)`) — with no server restart, and conforming
  clients re-list automatically. This is the runtime face of the A1/A2 mapping pipeline.
- **Governance holds:** only human-ratified mappings under `$ARIADNE_MAPPINGS` can be
  activated; the agent never introspects/applies a raw DSN. Runtime *activation* is the
  in-bounds slice of "adaptive."
- The official-SDK manual-notification path (and its request-context-only constraint) is
  captured here, so the next person doesn't reach for `jlowin/fastmcp`'s auto-notify and
  find it absent.
- One honest redundancy: `workup_<name>` overlaps the `dataset=` parameter. Justified by
  selection ergonomics + the need for a `list_changed`-bearing artifact; revisited if the
  per-dataset family grows (e.g. a dataset-scoped search tool).
- Tool-count growth is bounded — 2026 guidance is that clients handle hundreds of tools;
  if a deployment activates very many datasets we revisit (e.g. a single
  `workup` + resource-list), but that is not today's scale (YAGNI).

Sources: MCP tools + `listChanged` — [MCP spec, tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools);
runtime onboarding of new data sources without restart —
[Data API builder MCP](https://learn.microsoft.com/en-us/azure/data-api-builder/mcp/overview),
[Google MCP Toolbox for Databases](https://cloud.google.com/blog/products/ai-machine-learning/mcp-toolbox-for-databases-now-supports-model-context-protocol);
intent-named tools aid selection (not tool-explosion) —
[MCP server anti-patterns, 2026](https://www.digitalapplied.com/blog/mcp-server-anti-patterns-design-mistakes-2026-developer-guide);
manual notification is required on the official SDK (auto-notify is the separate package) —
[FastMCP tools](https://gofastmcp.com/servers/tools).
