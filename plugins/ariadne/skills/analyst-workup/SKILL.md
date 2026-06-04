---
name: analyst-workup
description: Produce a citation-grounded analytic note for a target entity across all available stores. Use when the user says "work up an entity", "sensemaking on a person/org", "who is X and how are they connected", "run a workup on X", or asks for entity intelligence/analysis.
disable-model-invocation: false
allowed-tools: mcp__ariadne__workup
---

# Analyst workup

Call the `workup` tool from the bundled `ariadne` MCP server.

## Invocation

- Required: `entity` — the name or ID of the target entity.
- Optional: `dataset` — defaults to `synthetic`; pass the actual dataset name if the user specifies one.
- Optional: `profile` — model + operating envelope from the deployment's curated allowlist; `list_profiles` returns the available names.
- Optional: `sql=true` — include the relational store.
- Optional: `semantic=true` — include the semantic (vector) store.

## Output contract

The server returns a cited analytic note. Every factual claim carries a `[cite:gN]` inline source tag. Present the note verbatim; do not infer, extend, or fabricate facts beyond it.

## Prerequisites

The Ariadne MCP server requires:
- Neo4j (graph store) reachable at `NEO4J_URI`.
- PostgreSQL (relational store) if `sql=true`.
- Qdrant (semantic store) if `semantic=true`.
- `ANTHROPIC_API_KEY` set in the environment.

If the server is unreachable, tell the user to verify the stores are running and the env vars are configured. For a local-checkout install, swap the MCP command in `.mcp.json` to `{"command": "python", "args": ["-m", "ariadne.mcp_server"]}`.
