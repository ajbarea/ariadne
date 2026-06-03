# Phase B3.2 — Semantic Search as a Live Agent Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox (`- [ ]`) steps.

**Goal:** Expose B3.1's `hybrid_search` to the live agent as an in-process SDK tool (`mcp__ariadne__hybrid_search`), wired into `workup` + the provenance/citation hook + the `entity-workup` skill — so a workup semantically + lexically searches email-body documents and cites them. This realizes ADR-0007's hybrid retrieval in the live loop.

**Architecture:** A `create_sdk_mcp_server`-based in-process tool (claude-agent-sdk 0.2.87 `@tool` + `create_sdk_mcp_server`) embeds the agent's query, runs the RRF `hybrid_search` against Postgres, and returns ranked email passages. `build_options(..., with_semantic=True)` registers the server, allows the tool, and adds `mcp__ariadne__` to the provenance hook so results get `[cite:gN]` ids. A `--semantic` CLI flag opts in.

**Tech Stack:** Python 3.14, `uv`, `ruff`, `pytest`; claude-agent-sdk in-process tools; the `embed` extra (real embedder at workup time); psycopg. ENV: pytest is `uv run python -m pytest …` (NOT `uv run pytest`). The live end-to-end (agent actually calls the tool) needs `ANTHROPIC_API_KEY` + live Neo4j/Postgres + indexed data — a manual/gated smoke, not a hermetic gate.

> **SDK facts (verified, 0.2.87):** `tool(name, description, input_schema: dict)` decorates an `async def fn(args: dict) -> dict` returning `{"content": [{"type": "text", "text": ...}]}`; `create_sdk_mcp_server(name, version, tools=[...]) -> McpSdkServerConfig`. The agent sees the tool as `mcp__<server>__<tool>` → here `mcp__ariadne__hybrid_search`.

> **Commits:** plain messages, NO Co-Authored-By / "Generated with" / 🤖. Gate: `make lint && uv run python -m pytest tests/unit tests/test_smoke.py -q`.

---

### Task 1: The in-process hybrid-search tool

**Files:**
- Create: `src/ariadne/unstructured/search_tool.py`
- Test: `tests/unit/test_search_tool.py` (hermetic), `tests/integration/test_search_tool_live.py` (gated, pgvector image + fake embedder)

- [ ] **Step 1: Hermetic test** (`tests/unit/test_search_tool.py`) — covers the pure formatting + the server construction shape (no DB, no agent):

```python
from __future__ import annotations

from ariadne.unstructured.search_tool import ARIADNE_TOOLS, _format_content, make_ariadne_server
from ariadne.unstructured.embed import FakeEmbedder


def test_format_content_wraps_passages_for_the_agent() -> None:
    out = _format_content([{"id": "email:1", "text": "the shipment leaves at dawn"}])
    assert out["content"][0]["type"] == "text"
    assert "email:1" in out["content"][0]["text"] and "shipment" in out["content"][0]["text"]


def test_format_content_handles_no_results() -> None:
    out = _format_content([])
    assert "No matching" in out["content"][0]["text"]


def test_tool_name_constant() -> None:
    assert ARIADNE_TOOLS == ["mcp__ariadne__hybrid_search"]


def test_make_ariadne_server_builds_an_sdk_server() -> None:
    server = make_ariadne_server({"DATABASE_URI": "postgresql://x"}, FakeEmbedder(dim=8))
    assert server is not None  # an McpSdkServerConfig; constructed without touching the DB
```

- [ ] **Step 2: run** → FAIL.

- [ ] **Step 3: Implement** `src/ariadne/unstructured/search_tool.py`:

```python
"""In-process hybrid-search tool for the live agent loop (ADR-0007 / B3.2).

Exposes ``mcp__ariadne__hybrid_search`` so the agent can semantically + lexically
search email-body Documents (RRF-fused) and cite the results like any other
evidence. The DB connection is opened per call from ``DATABASE_URI``; the
embedder is injected.
"""

from __future__ import annotations

from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from ariadne.unstructured.document_store import hybrid_search

ARIADNE_TOOLS = ["mcp__ariadne__hybrid_search"]
_DEFAULT_DSN = "postgresql://ariadne:ariadne@localhost:5432/intel"
_SNIPPET = 1000


def search_documents(conn, query: str, embedder, *, limit: int = 5) -> list[dict]:
    """RRF-fused ids (B3.1) joined back to their text, preserving rank order."""
    ids = hybrid_search(conn, query, embedder, limit=limit)
    if not ids:
        return []
    rows = conn.execute(
        b"SELECT id, text FROM documents WHERE id = ANY(%(ids)s)", {"ids": ids}
    ).fetchall()
    by_id = {r[0]: r[1] for r in rows}
    return [{"id": i, "text": by_id.get(i, "")} for i in ids]


def _format_content(results: list[dict]) -> dict[str, Any]:
    if not results:
        return {"content": [{"type": "text", "text": "No matching documents."}]}
    blocks = [f"[{r['id']}] {r['text'][:_SNIPPET]}" for r in results]
    return {"content": [{"type": "text", "text": "\n\n".join(blocks)}]}


def make_ariadne_server(env: dict[str, str], embedder):
    """Build the in-process SDK MCP server exposing the hybrid-search tool."""
    dsn = env.get("DATABASE_URI", _DEFAULT_DSN)

    @tool(
        "hybrid_search",
        "Hybrid (full-text + semantic) search over email-body documents. "
        "Returns ranked passages with their ids; cite facts you use as [cite:gN].",
        {"query": str, "limit": int},
    )
    async def hybrid_search_tool(args: dict) -> dict[str, Any]:
        import psycopg

        query = str(args["query"])
        limit = int(args.get("limit", 5))
        with psycopg.connect(dsn, autocommit=True) as conn:
            results = search_documents(conn, query, embedder, limit=limit)
        return _format_content(results)

    return create_sdk_mcp_server("ariadne", tools=[hybrid_search_tool])
```

- [ ] **Step 4: run** unit → PASS (4). `make lint` clean. (If `create_sdk_mcp_server`/`tool` import fails, the SDK version differs — STOP and report; do not work around.)

- [ ] **Step 5: Gated integration test** (`tests/integration/test_search_tool_live.py`) — proves `search_documents` end-to-end (pgvector image + FakeEmbedder), reusing the B3.1 setup:

```python
"""search_documents over a live pgvector store (gated)."""

from __future__ import annotations

import pytest

pytest.importorskip("testcontainers")
pytest.importorskip("psycopg")

import psycopg
from testcontainers.postgres import PostgresContainer

from ariadne.datasets.canonical import Document
from ariadne.unstructured.document_store import (
    ensure_schema, ensure_vector_schema, store_embeddings, upsert_documents,
)
from ariadne.unstructured.embed import FakeEmbedder
from ariadne.unstructured.search_tool import search_documents

pytestmark = pytest.mark.integration


def test_search_documents_returns_ranked_passages() -> None:
    emb = FakeEmbedder(dim=8)
    with PostgresContainer("pgvector/pgvector:pg17") as pg:
        info = (f"host={pg.get_container_host_ip()} port={pg.get_exposed_port(5432)} "
                f"user={pg.username} password={pg.password} dbname={pg.dbname}")
        with psycopg.connect(info, autocommit=True) as conn:
            ensure_schema(conn)
            ensure_vector_schema(conn, dim=emb.dim)
            docs = [Document(id="a", text="the shipment leaves Compound-Alpha at dawn"),
                    Document(id="b", text="quarterly budget review notes")]
            upsert_documents(conn, docs)
            store_embeddings(conn, {d.id: emb.embed([d.text])[0] for d in docs})
            results = search_documents(conn, "Compound-Alpha shipment", emb, limit=3)
            assert results and results[0]["id"] == "a"
            assert "shipment" in results[0]["text"]
```

- [ ] **Step 6: run integration** (Colima up) → 1 passed.

- [ ] **Step 7: full suite + lint + commit.** `feat(unstructured): in-process hybrid_search agent tool (mcp__ariadne__)`

---

### Task 2: Provenance hook records the ariadne tool

**Files:**
- Modify: `src/ariadne/provenance/hook.py`
- Test: `tests/unit/test_provenance_hook.py` (extend)

- [ ] **Step 1: Extend the failing test** — add to `tests/unit/test_provenance_hook.py` (match the existing style; the existing tests build a `PostToolUseHookInput`-like dict and assert the ledger records evidence-tool calls):

```python
def test_hook_records_ariadne_search_calls() -> None:
    # mirror the existing test that checks mcp__postgres__ is recorded, but for the
    # in-process semantic tool mcp__ariadne__hybrid_search.
    ledger = ProvenanceLedger()
    hook = make_provenance_hook(ledger)
    # ... build the same PostToolUse input shape the other tests use, with
    # tool name "mcp__ariadne__hybrid_search" and a text response, invoke the hook,
    # and assert ledger.entries has one entry whose tool is the ariadne search.
```
(Read the existing `test_hook_records_relational_calls_too` test in this file and copy its exact construction, substituting the `mcp__ariadne__hybrid_search` tool name.)

- [ ] **Step 2: run** → FAIL (ariadne prefix not recorded).

- [ ] **Step 3: Implement** in `src/ariadne/provenance/hook.py`:
- Add `"mcp__ariadne__"` to `EVIDENCE_TOOL_PREFIXES`:
```python
EVIDENCE_TOOL_PREFIXES = ("mcp__neo4j__", "mcp__postgres__", "mcp__ariadne__")
```
- Add a `_source_label` case:
```python
    if tool.startswith("mcp__ariadne__"):
        return "text"
```
(place it alongside the existing graph/relational branches).

- [ ] **Step 4: run** the extended test + the whole hook test file → PASS. Full suite → no regression. `make lint` clean.

- [ ] **Step 5: Commit** `feat(provenance): record mcp__ariadne__ semantic-search calls for citation`

---

### Task 3: Wire `--semantic` into build_options + CLI

**Files:**
- Modify: `src/ariadne/cli.py`
- Test: `tests/unit/test_build_options.py` (extend), `tests/unit/test_cli_dataset_flag.py` or a new `tests/unit/test_cli_semantic_flag.py`

- [ ] **Step 1: Extend the failing test** — in `tests/unit/test_build_options.py` add (match existing style which calls `build_options(ledger=..., env=..., with_sql=...)` and asserts on `allowed_tools`/`mcp_servers`):

```python
def test_with_semantic_adds_the_ariadne_tool_and_server() -> None:
    from ariadne.cli import build_options
    from ariadne.provenance.ledger import ProvenanceLedger
    opts = build_options(ledger=ProvenanceLedger(),
                         env={"DATABASE_URI": "postgresql://x"}, with_semantic=True)
    assert "mcp__ariadne__hybrid_search" in opts.allowed_tools
    assert "ariadne" in opts.mcp_servers
```

And a CLI flag test (new `tests/unit/test_cli_semantic_flag.py`):
```python
from __future__ import annotations
from ariadne.cli import parse_args

def test_workup_semantic_flag_defaults_false() -> None:
    assert parse_args(["workup", "X"]).semantic is False

def test_workup_semantic_flag_opts_in() -> None:
    assert parse_args(["workup", "X", "--semantic"]).semantic is True
```

- [ ] **Step 2: run** → FAIL.

- [ ] **Step 3: Implement** in `src/ariadne/cli.py`:
- `parse_args` workup parser: add `wk.add_argument("--semantic", action="store_true", help="Enable semantic+full-text search over email bodies (needs the 'embed' extra + Postgres).")`.
- `build_options` signature: add `with_semantic: bool = False`. Inside, after the `with_sql` block:
```python
    if with_semantic:
        from ariadne.unstructured.embed import SentenceTransformerEmbedder
        from ariadne.unstructured.search_tool import ARIADNE_TOOLS, make_ariadne_server

        embedder = SentenceTransformerEmbedder()
        mcp_servers["ariadne"] = make_ariadne_server(env, embedder)
        allowed_tools += list(ARIADNE_TOOLS)
        matchers.append(HookMatcher(matcher="mcp__ariadne__.*", hooks=[hook]))
```
- `run_workup` signature: add `with_semantic: bool = False`; thread it into `build_options(...)`.
- `main` workup dispatch: pass `with_semantic=args.semantic`.

- [ ] **Step 4: run** both test files + full suite → no regression. `make lint` clean. (Constructing `SentenceTransformerEmbedder()` in `build_options` does NOT load the model — `_load` is lazy — so `test_with_semantic...` stays hermetic. Confirm the test passes WITHOUT the embed extra installed.)

- [ ] **Step 5: Commit** `feat(cli): --semantic wires the hybrid-search tool into the workup loop`

---

### Task 4: Skill guidance + docs

**Files:** `.claude/skills/entity-workup/SKILL.md`, `IMPL.md`, `ROADMAP.md`, `docs/architecture/index.md`

- [ ] **Step 1:** `entity-workup/SKILL.md` — update the free-text/email guidance (B1 added a full-text-via-`execute_sql` note): when the `mcp__ariadne__hybrid_search` tool is available, prefer it for email-body / free-text evidence (it fuses full-text + semantic and returns ranked passages with ids to cite). Keep terse. Don't remove the graph/SQL routing.
- [ ] **Step 2:** `IMPL.md` — "Phase B3.2 shipped": in-process `mcp__ariadne__hybrid_search` tool + `--semantic` flag + provenance/citation wiring; ADR-0007 now realized in the live loop. Reference this plan.
- [ ] **Step 3:** `ROADMAP.md` — mark B3.2 done; note ADR-0007 hybrid retrieval is now complete end-to-end. The live Kaminski demo now exercises graph + full-text + semantic.
- [ ] **Step 4:** `docs/architecture/index.md` — one sentence: the agent reaches hybrid retrieval via the in-process `mcp__ariadne__hybrid_search` tool (opt-in `--semantic`).
- [ ] **Step 5:** `uv run --with zensical zensical build` → "No issues found". `make lint` + full suite green. Commit `docs: Phase B3.2 (semantic agent tool) notes + skill guidance`.

---

## Phase B3.2 done (all true)

1. `make_ariadne_server` builds an in-process SDK MCP server exposing `mcp__ariadne__hybrid_search`; `search_documents` returns ranked passages (integration-proven on pgvector).
2. The provenance hook records `mcp__ariadne__` calls so semantic-search results get `[cite:gN]` ids.
3. `build_options(with_semantic=True)` / `ariadne workup … --semantic` registers the tool, allows it, and hooks it.
4. The `entity-workup` skill tells the agent to use it for email-body evidence.
5. `make lint` + full unit/smoke green; gated integration green.

## Manual live smoke (the payoff — not a hermetic gate)

`uv sync --extra data --extra embed`; bring up Neo4j + Postgres (`docker compose -f infra/neo4j/... up`, `infra/postgres/... up`) with pgvector; `ariadne index --dataset enron`; then
`ariadne workup vince.kaminski@enron.com --dataset enron --sql --semantic` — the agent traverses the comm graph, full-text + semantically searches email bodies, and produces a cited note (e.g. surfacing the `vkaminski@aol.com` cross-account tie); `ariadne eval <dir> --fixture kaminski-aol`.
