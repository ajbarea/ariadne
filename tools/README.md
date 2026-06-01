# tools/

Custom, in-process agent tools — connectors and modality-specific processors
exposed to the harness. **Empty until the research sets the MVP toolset.**

Per the [SDK reference](../docs/research/claude-agent-sdk-reference.md), prefer
in-process SDK tools for app-specific logic and fast iteration; promote a tool to
an [MCP server](../mcp_servers/) when it should be reusable across projects or
run as a separate process. Anticipated early tools (provisional — confirm against
research): a graph-store query tool, a provenance recorder, an entity-resolution
lookup. Each new tool gets a `# research(YYYY-MM):` note in
[`../ROADMAP.md`](../ROADMAP.md).
