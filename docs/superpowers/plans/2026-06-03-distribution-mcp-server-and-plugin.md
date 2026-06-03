# Distribution — MCP Server + Claude Code Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox (`- [ ]`) steps.

**Goal:** Make Ariadne usable from any AI CLI and one-click-installable in Claude Code (ADR-0009). Part 1 = an `ariadne` MCP server (FastMCP) wrapping the harness as a `workup` tool. Part 2 = a Claude Code plugin (techne-style) that bundles the server + a sensemaking skill.

**Architecture:** `src/ariadne/mcp_server.py` uses `mcp.server.fastmcp.FastMCP` (already installed via claude-agent-sdk) to expose `workup(entity, dataset, sql, semantic)` — which runs the existing `run_workup` harness internally and returns the cited note — plus a `hybrid_search(query)` composition tool. The testable core (`run_workup_tool`) is separated from the FastMCP decorator so it's hermetically unit-tested with a fake runner. The plugin (Part 2) is a repo-as-marketplace bundle mirroring `~/ajsoftworks/techne`.

**Tech Stack:** Python 3.14, `uv`, `ruff`, `pytest`; `mcp.server.fastmcp.FastMCP` (in `mcp`, already a transitive dep — pin it as a direct dep). ENV: pytest is `uv run python -m pytest …`. The real `workup` tool needs `ANTHROPIC_API_KEY` + live stores (manual smoke, not a hermetic gate).

> **Commits:** plain messages, NO Co-Authored-By / "Generated with" / 🤖. Gate: `make lint && uv run python -m pytest tests/unit tests/test_smoke.py -q`.

---

## PART 1 — the MCP server (build first)

### Task 1: `ariadne` MCP server module

**Files:**
- Modify: `pyproject.toml` (pin `mcp>=1.2` in `dependencies`; add `[project.scripts] ariadne-mcp = "ariadne.mcp_server:main"`), `uv.lock`
- Create: `src/ariadne/mcp_server.py`
- Test: `tests/unit/test_mcp_server.py` (hermetic)

- [ ] **Step 1: Hermetic test** (`tests/unit/test_mcp_server.py`):

```python
from __future__ import annotations

import asyncio
from pathlib import Path

from ariadne.mcp_server import mcp, run_workup_tool


def test_server_is_named_ariadne() -> None:
    assert mcp.name == "ariadne"


def test_run_workup_tool_returns_the_note(tmp_path) -> None:
    # Inject a fake runner that writes a note and returns 0 (no agent loop / API key).
    async def fake_runner(entity, out_root, env, *, with_sql, dataset, with_semantic):
        d = Path(out_root) / "halberd"
        d.mkdir(parents=True, exist_ok=True)
        (d / "note.md").write_text("# Workup\nHalberd is co-located at Compound-Alpha [cite:g1].")
        return 0

    note = asyncio.run(run_workup_tool(
        "Halberd", dataset="synthetic", sql=False, semantic=False,
        env={}, runner=fake_runner, out_root=str(tmp_path), slug="halberd",
    ))
    assert "Compound-Alpha" in note and "[cite:g1]" in note


def test_run_workup_tool_reports_when_no_note(tmp_path) -> None:
    async def fake_runner(entity, out_root, env, *, with_sql, dataset, with_semantic):
        return 1  # produced nothing

    note = asyncio.run(run_workup_tool(
        "Nobody", env={}, runner=fake_runner, out_root=str(tmp_path), slug="nobody",
    ))
    assert "no analytic note" in note.lower()
```

- [ ] **Step 2: run** → FAIL.

- [ ] **Step 3: Implement** `src/ariadne/mcp_server.py`:

```python
"""Ariadne as an MCP server — usable from any MCP client (ADR-0009).

Exposes the whole harness as a single ``workup`` tool: a host agent (Claude
Code, Copilot, Gemini CLI, Cursor, …) calls it and Ariadne runs its own
gather→act→verify→synthesize loop internally, returning the cited analytic note.
A ``hybrid_search`` tool is offered for composition. Run as ``ariadne-mcp``
(stdio) or ``python -m ariadne.mcp_server``.

Config caveat: the tool is portable, the data is not — point the server at your
stores (NEO4J_*/DATABASE_URI) + ANTHROPIC_API_KEY per install.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "ariadne",
    instructions="Rigorous, citation-grounded entity sensemaking over heterogeneous "
    "stores. Use `workup` to produce a cited analytic note for a target entity.",
)

_Runner = Callable[..., Awaitable[int]]


def _slug(entity: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in entity).strip("-").lower() or "entity"


async def run_workup_tool(
    entity: str,
    *,
    dataset: str = "synthetic",
    sql: bool = False,
    semantic: bool = False,
    env: dict[str, str] | None = None,
    runner: _Runner | None = None,
    out_root: str | None = None,
    slug: str | None = None,
) -> str:
    """Run a workup and return the cited note text (testable core, DI'd runner)."""
    if runner is None:
        from ariadne.cli import run_workup as runner  # noqa: PLW0127
    env = os.environ if env is None else env  # type: ignore[assignment]
    out_root = out_root or tempfile.mkdtemp(prefix="ariadne-mcp-")
    slug = slug or _slug(entity)
    await runner(entity, out_root, dict(env), with_sql=sql, dataset=dataset, with_semantic=semantic)
    note = Path(out_root) / slug / "note.md"
    if note.exists():
        return note.read_text(encoding="utf-8")
    return f"Workup for {entity!r} produced no analytic note (check stores / API key)."


@mcp.tool()
async def workup(
    entity: str, dataset: str = "synthetic", sql: bool = False, semantic: bool = False
) -> str:
    """Produce a rigorous, citation-grounded analytic note for a target entity.

    Traverses the graph + (optionally) relational and semantic stores, reconciles
    across sources, and returns a note where every fact carries a [cite:gN] source.
    """
    return await run_workup_tool(entity, dataset=dataset, sql=sql, semantic=semantic)


@mcp.tool()
async def hybrid_search(query: str, limit: int = 5) -> dict[str, Any]:
    """Full-text + semantic (RRF) search over indexed email-body documents."""
    from ariadne.unstructured.embed import SentenceTransformerEmbedder
    from ariadne.unstructured.search_tool import _format_content, search_documents
    import psycopg

    dsn = os.environ.get("DATABASE_URI", "postgresql://ariadne:ariadne@localhost:5432/intel")
    with psycopg.connect(dsn, autocommit=True) as conn:
        results = search_documents(conn, query, SentenceTransformerEmbedder(), limit=limit)
    return _format_content(results)


def main() -> None:
    """Entry point — runs the stdio MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: run** `uv run python -m pytest tests/unit/test_mcp_server.py -q` → PASS (3). `make lint` clean. (If `mcp` isn't a direct dep yet, `uv lock` after adding it to `pyproject.toml [project] dependencies`.)

- [ ] **Step 5: Smoke the server starts** (no agent loop): `uv run python -c "from ariadne.mcp_server import mcp; print('tools:', sorted(t.name for t in mcp._tool_manager.list_tools()))"` should list `hybrid_search` and `workup` (if the introspection attribute differs, just confirm the module imports + `mcp.name=='ariadne'`; don't depend on private internals in the committed test).

- [ ] **Step 6: full suite + lint + commit.** `feat(mcp): ariadne MCP server (workup + hybrid_search tools) for any MCP client`

---

### Task 2: docs — the MCP server

**Files:** `README.md`, `IMPL.md`, `ROADMAP.md`, `docs/architecture/index.md`

- [ ] `README.md` — a short "Use from any AI CLI" section: `uvx ariadne-mcp` (or add to a client's MCP config) exposes the `workup` tool; note the per-install store/key config. `IMPL.md` — "MCP server shipped" entry. `ROADMAP.md` — distribution: MCP server done (Part 1), plugin bundle next (Part 2), ADR-0009. `docs/architecture/index.md` — one line: Ariadne is consumable as an MCP server (ADR-0009). Build docs clean; commit `docs: MCP server (distribution Part 1) notes`.

---

## PART 2 — the Claude Code plugin (after the server)

### Task 3: plugin bundle (mirrors techne)

**Files (all new):**
- `.claude-plugin/marketplace.json`
- `plugins/ariadne/.claude-plugin/plugin.json`
- `plugins/ariadne/.mcp.json`
- `plugins/ariadne/skills/analyst-workup/SKILL.md`

- [ ] **Step 1:** `.claude-plugin/marketplace.json` (mirror techne's): name `ariadne`, owner AJ, one plugin entry `{ "name": "ariadne", "source": "./plugins/ariadne", "category": "analysis" }`.
- [ ] **Step 2:** `plugins/ariadne/.claude-plugin/plugin.json`: name/description/author/repository/homepage/license/keywords (mirror techne's plugin.json shape).
- [ ] **Step 3:** `plugins/ariadne/.mcp.json` — bundle the server:
```json
{ "mcpServers": { "ariadne": { "command": "uvx", "args": ["ariadne-mcp"] } } }
```
(Document that `uvx ariadne-mcp` requires the package published, or use `{"command": "python", "args": ["-m", "ariadne.mcp_server"]}` for a local checkout.)
- [ ] **Step 4:** `plugins/ariadne/skills/analyst-workup/SKILL.md` — a skill (YAML frontmatter `name`, `description`) that tells the host agent: to work up an entity, call the `workup` MCP tool (from the bundled `ariadne` server) with the entity + dataset; present the returned cited note. Terse.
- [ ] **Step 5:** Validate JSON (`python -c "import json; [json.load(open(p)) for p in [...]]"`); confirm the marketplace/plugin shape matches techne. Commit `feat(plugin): ariadne Claude Code plugin bundling the MCP server + analyst-workup skill`.

---

## Done (all true)

1. `ariadne-mcp` runs a FastMCP stdio server exposing `workup` + `hybrid_search`; `run_workup_tool` returns the cited note (hermetic, DI'd runner).
2. The plugin bundle mirrors techne (marketplace.json + plugins/ariadne/{plugin.json, .mcp.json, skill}); JSON valid.
3. `make lint` + full unit/smoke green.
4. Manual smoke (documented): add the server to any MCP CLI / install the plugin in Claude Code → call `workup`.

## Manual smoke (the payoff)
`uv run python -m ariadne.mcp_server` (or add `{"command":"python","args":["-m","ariadne.mcp_server"]}` to a CLI's MCP config), with stores up + API key, then ask the host agent to "work up Halberd" → it calls the `workup` tool and returns the cited note. In Claude Code: install the plugin from the local marketplace, then `/ariadne` or "work up …".
