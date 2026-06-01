# Phase 1 Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Ariadne's single-store vertical slice — `ariadne workup <entity>` runs the live Claude Agent SDK loop against a read-only Neo4j graph and emits a cited analytic note plus a provenance ledger, with every fact traceable to the graph call that sourced it.

**Architecture:** The graph connector is the official `mcp-neo4j-cypher` MCP server (stdio, read-only) — we do not hand-roll query execution. We own four pure/hermetic units (provenance ledger + `PostToolUse` hook, citation validator, output persistence, stdio-config builder), an `entity-workup` skill, and a CLI that assembles `ClaudeAgentOptions` and runs the agent loop. A `PostToolUse` hook (transport-agnostic) records every `mcp__neo4j__*` call and hands the agent a `[cite:gN]` id to cite; a validator enforces that every citation resolves to a ledger entry.

**Tech Stack:** Python 3.12+, `claude-agent-sdk`, `neo4j` driver, `mcp-neo4j-cypher` server, `uv`, `ruff`, `ty`, `pytest`, `testcontainers[neo4j]`, Docker (Colima).

**Spec:** [`docs/superpowers/specs/2026-06-01-phase-1-vertical-slice-design.md`](../specs/2026-06-01-phase-1-vertical-slice-design.md)

---

## File structure

| File | Responsibility |
| ---- | -------------- |
| `src/ariadne/provenance/__init__.py` | package marker |
| `src/ariadne/provenance/ledger.py` | `ProvenanceLedger` — assigns `gN` ids, holds entries, writes jsonl |
| `src/ariadne/provenance/hook.py` | `make_provenance_hook(ledger)` — the `PostToolUse` SDK callback factory |
| `src/ariadne/provenance/citations.py` | `extract_citations`, `validate_citations`, `CitationReport` |
| `src/ariadne/report/__init__.py` | package marker |
| `src/ariadne/report/note.py` | `write_outputs` — persist note.md, provenance.jsonl, citations.json |
| `src/ariadne/graph/__init__.py` | package marker |
| `src/ariadne/graph/neo4j_server.py` | `neo4j_stdio_config` — build the `mcp-neo4j-cypher` stdio config from env |
| `src/ariadne/cli.py` | arg parsing, `build_options`, `run_workup`, `main` |
| `src/ariadne/__main__.py` | delegate to `cli.main` (modify) |
| `.claude/skills/entity-workup/SKILL.md` | the gather→act→verify→synthesize workflow |
| `.claude/skills/entity-workup/note-template.md` | analytic-note template |
| `infra/neo4j/docker-compose.yml` | local Neo4j service |
| `infra/neo4j/seed.cypher` | synthetic org-hierarchy seed with a planted multi-hop link |
| `tests/unit/*` | hermetic unit tests |
| `tests/integration/*` | testcontainers Neo4j + live agent (key-gated) |
| `tests/fixtures/*` | recorded MCP tool-response JSON |

---

## Task 1: Add dependencies and verify SDK API shapes

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add runtime + dev deps with research notes**

In `pyproject.toml`, replace `dependencies = []` with:

```toml
dependencies = [
    # research(2026-06): Claude Agent SDK is the harness (orchestrator–worker loop,
    # tools/skills/hooks/MCP). See docs/research/claude-agent-sdk-reference.md.
    "claude-agent-sdk>=0.1",
    # research(2026-06): official Neo4j Python driver — used to seed/health-check the
    # graph and by integration tests. Neo4j is the production graph standard (D1/D4).
    "neo4j>=5.28",
    # research(2026-06): official Neo4j MCP server is the read-only graph connector;
    # gives schema introspection, query timeouts, token-aware truncation, injection-safe
    # parameterization for free (D1). Launched via uvx in cli; pinned here for clarity.
    "mcp-neo4j-cypher>=0.6,<0.7",
]
```

In `[dependency-groups]` `dev = [...]`, add:

```toml
    "testcontainers[neo4j]>=4.9",
```

- [ ] **Step 2: Sync and verify the install resolves**

Run: `uv sync --group dev`
Expected: resolves and installs without error; `claude-agent-sdk`, `neo4j`, `mcp-neo4j-cypher`, `testcontainers` appear in the output.

- [ ] **Step 3: Verify the real SDK symbol names (fast-moving dep)**

Run:
```bash
uv run --no-active python -c "import claude_agent_sdk as s; print([n for n in dir(s) if any(k in n for k in ('query','Options','Hook','Message','TextBlock','mcp'))])"
uv run --no-active python -c "from claude_agent_sdk import HookMatcher; import inspect; print(inspect.signature(HookMatcher.__init__) if inspect.isclass(HookMatcher) else HookMatcher)"
```
Expected: prints exported symbols including `query`, `ClaudeAgentOptions`, `HookMatcher`, `AssistantMessage`, `TextBlock`, `ResultMessage`. Note the **actual `HookMatcher` shape** — this plan's hook code uses `HookMatcher(matcher="mcp__neo4j__.*", hooks=[fn])`. If the installed version instead wants a dict (`{"matcher": {...}, "hooks": [...]}`), use that form in Task 8 and adjust the `hooks=` argument accordingly. Everything else in the plan is independent of this shape.

- [ ] **Step 4: Confirm the connector server launches**

Run: `uvx mcp-neo4j-cypher@0.6.0 --help`
Expected: prints usage including `--transport` and read-only/namespace options (no Neo4j connection needed for `--help`).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: add claude-agent-sdk, neo4j, mcp-neo4j-cypher deps for Phase 1"
```

---

## Task 2: ProvenanceLedger

**Files:**
- Create: `src/ariadne/provenance/__init__.py`
- Create: `src/ariadne/provenance/ledger.py`
- Test: `tests/unit/test_provenance_ledger.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_provenance_ledger.py`:
```python
from __future__ import annotations

import json

from ariadne.provenance.ledger import ProvenanceLedger


def test_record_assigns_sequential_ids() -> None:
    led = ProvenanceLedger()
    k1 = led.record("mcp__neo4j__read_neo4j_cypher", {"query": "MATCH (n) RETURN n"}, "rows...")
    k2 = led.record("mcp__neo4j__get_neo4j_schema", {}, "schema...")
    assert k1 == "g1"
    assert k2 == "g2"
    assert led.has("g1") and led.has("g2")
    assert not led.has("g3")


def test_entries_capture_tool_input_and_response() -> None:
    led = ProvenanceLedger()
    led.record("mcp__neo4j__read_neo4j_cypher", {"query": "Q"}, "RESP")
    (entry,) = led.entries
    assert entry["id"] == "g1"
    assert entry["tool"] == "mcp__neo4j__read_neo4j_cypher"
    assert entry["tool_input"] == {"query": "Q"}
    assert "RESP" in entry["response_excerpt"]
    assert "ts" in entry


def test_response_excerpt_is_truncated() -> None:
    led = ProvenanceLedger(excerpt_chars=10)
    led.record("t", {}, "x" * 500)
    assert len(led.entries[0]["response_excerpt"]) <= 10


def test_write_jsonl_round_trips(tmp_path) -> None:
    led = ProvenanceLedger()
    led.record("t", {"a": 1}, "r")
    path = tmp_path / "provenance.jsonl"
    led.write_jsonl(path)
    lines = path.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["id"] == "g1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-active pytest tests/unit/test_provenance_ledger.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ariadne.provenance'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/ariadne/provenance/__init__.py`:
```python
"""Provenance: the audit ledger, the PostToolUse hook, and citation validation."""
```

Create `src/ariadne/provenance/ledger.py`:
```python
"""Provenance ledger — records every graph tool call and assigns a citation id.

Each ``mcp__neo4j__*`` call the agent makes is recorded here as ``gN`` (g1, g2, …).
The agent cites facts as ``[cite:gN]``; the citation validator checks coverage.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class ProvenanceLedger:
    """An append-only, in-memory ledger of graph tool calls for one workup run."""

    def __init__(self, excerpt_chars: int = 2000) -> None:
        self._entries: list[dict[str, Any]] = []
        self._excerpt_chars = excerpt_chars

    def record(self, tool: str, tool_input: dict[str, Any], response: str) -> str:
        """Record a tool call and return its assigned citation id (``gN``)."""
        cite_id = f"g{len(self._entries) + 1}"
        self._entries.append(
            {
                "id": cite_id,
                "ts": datetime.now(UTC).isoformat(),
                "tool": tool,
                "tool_input": tool_input,
                "response_excerpt": str(response)[: self._excerpt_chars],
            }
        )
        return cite_id

    @property
    def entries(self) -> list[dict[str, Any]]:
        return list(self._entries)

    def has(self, cite_id: str) -> bool:
        return any(e["id"] == cite_id for e in self._entries)

    def write_jsonl(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for entry in self._entries:
                fh.write(json.dumps(entry) + "\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-active pytest tests/unit/test_provenance_ledger.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ariadne/provenance/__init__.py src/ariadne/provenance/ledger.py tests/unit/test_provenance_ledger.py
git commit -m "feat(provenance): add ProvenanceLedger with gN ids and jsonl output"
```

---

## Task 3: PostToolUse provenance hook

**Files:**
- Create: `src/ariadne/provenance/hook.py`
- Test: `tests/unit/test_provenance_hook.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_provenance_hook.py`:
```python
from __future__ import annotations

import pytest

from ariadne.provenance.hook import make_provenance_hook
from ariadne.provenance.ledger import ProvenanceLedger


@pytest.mark.asyncio
async def test_hook_records_graph_calls_and_returns_cite_context() -> None:
    led = ProvenanceLedger()
    hook = make_provenance_hook(led)
    out = await hook(
        {
            "tool_name": "mcp__neo4j__read_neo4j_cypher",
            "tool_input": {"query": "MATCH (n) RETURN n"},
            "tool_response": "rows...",
        },
        "tool-use-1",
        None,
    )
    assert led.has("g1")
    # The hook tells the agent which id to cite.
    blob = str(out)
    assert "g1" in blob and "cite" in blob.lower()


@pytest.mark.asyncio
async def test_hook_ignores_non_graph_tools() -> None:
    led = ProvenanceLedger()
    hook = make_provenance_hook(led)
    out = await hook(
        {"tool_name": "Read", "tool_input": {"file_path": "/x"}, "tool_response": "data"},
        "tool-use-2",
        None,
    )
    assert led.entries == []
    assert out == {}


@pytest.mark.asyncio
async def test_hook_reads_tool_output_fallback_key() -> None:
    led = ProvenanceLedger()
    hook = make_provenance_hook(led)
    await hook(
        {"tool_name": "mcp__neo4j__get_neo4j_schema", "tool_input": {}, "tool_output": "schema"},
        "tool-use-3",
        None,
    )
    assert "schema" in led.entries[0]["response_excerpt"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-active pytest tests/unit/test_provenance_hook.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ariadne.provenance.hook'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/ariadne/provenance/hook.py`:
```python
"""The PostToolUse provenance hook.

Fires after every tool call. For graph calls (``mcp__neo4j__*``) it records the
call in the ledger and returns an ``additionalContext`` string telling the agent
the ``[cite:gN]`` id to attach to facts derived from that result. The matcher is
transport-agnostic — this works against the external stdio Neo4j MCP server.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from ariadne.provenance.ledger import ProvenanceLedger

GRAPH_TOOL_PREFIX = "mcp__neo4j__"

Hook = Callable[[dict[str, Any], str | None, Any], Awaitable[dict[str, Any]]]


def make_provenance_hook(ledger: ProvenanceLedger) -> Hook:
    """Build a PostToolUse callback bound to ``ledger``."""

    async def provenance_hook(
        input_data: dict[str, Any],
        tool_use_id: str | None,
        context: Any,
    ) -> dict[str, Any]:
        tool = input_data.get("tool_name", "")
        if not tool.startswith(GRAPH_TOOL_PREFIX):
            return {}
        response = input_data.get("tool_response", input_data.get("tool_output", ""))
        cite_id = ledger.record(tool, input_data.get("tool_input", {}), response)
        return {
            "additionalContext": (
                f"Provenance: this graph result is recorded as {cite_id}. "
                f"Cite every fact you derive from it as [cite:{cite_id}]."
            )
        }

    return provenance_hook
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-active pytest tests/unit/test_provenance_hook.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Verify the additionalContext return key against the installed SDK**

Run: `uv run --no-active python -c "import claude_agent_sdk, inspect; print([n for n in dir(claude_agent_sdk) if 'Hook' in n or 'hook' in n])"`
Expected: confirms hook types. If the installed SDK does not honor `additionalContext` from `PostToolUse`, the ledger still records correctly (the unit tests above don't depend on the agent seeing it); the fallback citation path in the SKILL.md (Task 7, "cite graph queries in order g1, g2, …") still yields valid `[cite:gN]` ids. Leave the code as-is.

- [ ] **Step 6: Commit**

```bash
git add src/ariadne/provenance/hook.py tests/unit/test_provenance_hook.py
git commit -m "feat(provenance): add PostToolUse hook that records graph calls and emits cite ids"
```

---

## Task 4: Citation extraction and validator

**Files:**
- Create: `src/ariadne/provenance/citations.py`
- Test: `tests/unit/test_citation_validate.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_citation_validate.py`:
```python
from __future__ import annotations

from ariadne.provenance.citations import (
    CitationReport,
    extract_citations,
    validate_citations,
)
from ariadne.provenance.ledger import ProvenanceLedger


def test_extract_citations_finds_unique_ids_in_order() -> None:
    note = "Alpha reports to Bravo [cite:g1]. Bravo leads Unit-7 [cite:g2]. Recap [cite:g1]."
    assert extract_citations(note) == ["g1", "g2"]


def test_validate_passes_when_all_citations_resolve() -> None:
    led = ProvenanceLedger()
    led.record("mcp__neo4j__read_neo4j_cypher", {"query": "Q1"}, "r")
    led.record("mcp__neo4j__read_neo4j_cypher", {"query": "Q2"}, "r")
    report = validate_citations("Fact A [cite:g1]. Fact B [cite:g2].", led)
    assert isinstance(report, CitationReport)
    assert report.ok is True
    assert report.dangling == []
    assert report.unused == []


def test_validate_flags_dangling_citation() -> None:
    led = ProvenanceLedger()
    led.record("mcp__neo4j__read_neo4j_cypher", {"query": "Q1"}, "r")
    report = validate_citations("Real [cite:g1]. Fake [cite:g9].", led)
    assert report.ok is False
    assert report.dangling == ["g9"]


def test_validate_reports_unused_evidence() -> None:
    led = ProvenanceLedger()
    led.record("mcp__neo4j__read_neo4j_cypher", {"query": "Q1"}, "r")
    led.record("mcp__neo4j__read_neo4j_cypher", {"query": "Q2"}, "r")
    report = validate_citations("Only one fact [cite:g1].", led)
    assert report.ok is True  # unused is informational, not a failure
    assert report.unused == ["g2"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-active pytest tests/unit/test_citation_validate.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ariadne.provenance.citations'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/ariadne/provenance/citations.py`:
```python
"""Citation extraction and coverage validation.

The analytic note cites graph facts as ``[cite:gN]``. A note PASSES validation
only if every citation resolves to a ledger entry (no fabricated sources). This
is Ariadne's first concrete answer to "how do you know it works?".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ariadne.provenance.ledger import ProvenanceLedger

_CITE_RE = re.compile(r"\[cite:(g\d+)\]")


@dataclass(frozen=True)
class CitationReport:
    """Result of validating a note's citations against a ledger."""

    ok: bool
    cited: list[str]
    dangling: list[str]  # cited in the note but absent from the ledger (failure)
    unused: list[str]  # in the ledger but never cited (informational)


def extract_citations(note: str) -> list[str]:
    """Return unique ``gN`` ids in first-seen order."""
    seen: dict[str, None] = {}
    for match in _CITE_RE.finditer(note):
        seen.setdefault(match.group(1), None)
    return list(seen)


def validate_citations(note: str, ledger: ProvenanceLedger) -> CitationReport:
    cited = extract_citations(note)
    ledger_ids = [e["id"] for e in ledger.entries]
    dangling = [c for c in cited if not ledger.has(c)]
    unused = [i for i in ledger_ids if i not in cited]
    return CitationReport(ok=not dangling, cited=cited, dangling=dangling, unused=unused)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-active pytest tests/unit/test_citation_validate.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ariadne/provenance/citations.py tests/unit/test_citation_validate.py
git commit -m "feat(provenance): add citation extraction and coverage validator"
```

---

## Task 5: Output persistence

**Files:**
- Create: `src/ariadne/report/__init__.py`
- Create: `src/ariadne/report/note.py`
- Test: `tests/unit/test_note_outputs.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_note_outputs.py`:
```python
from __future__ import annotations

import json

from ariadne.provenance.citations import validate_citations
from ariadne.provenance.ledger import ProvenanceLedger
from ariadne.report.note import write_outputs


def test_write_outputs_creates_all_three_files(tmp_path) -> None:
    led = ProvenanceLedger()
    led.record("mcp__neo4j__read_neo4j_cypher", {"query": "Q"}, "r")
    note = "Finding [cite:g1]."
    report = validate_citations(note, led)

    write_outputs(tmp_path, entity="Alpha", note=note, ledger=led, report=report)

    assert (tmp_path / "note.md").read_text() == note
    assert (tmp_path / "provenance.jsonl").read_text().strip()
    citations = json.loads((tmp_path / "citations.json").read_text())
    assert citations["ok"] is True
    assert citations["cited"] == ["g1"]
    assert citations["entity"] == "Alpha"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-active pytest tests/unit/test_note_outputs.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ariadne.report'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/ariadne/report/__init__.py`:
```python
"""Report: persist the analytic note, provenance ledger, and citation report."""
```

Create `src/ariadne/report/note.py`:
```python
"""Persist a workup run's artifacts to an output directory."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ariadne.provenance.citations import CitationReport
from ariadne.provenance.ledger import ProvenanceLedger


def write_outputs(
    out_dir: str | Path,
    *,
    entity: str,
    note: str,
    ledger: ProvenanceLedger,
    report: CitationReport,
) -> None:
    """Write ``note.md``, ``provenance.jsonl`` and ``citations.json`` to ``out_dir``."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "note.md").write_text(note, encoding="utf-8")
    ledger.write_jsonl(out_dir / "provenance.jsonl")
    payload = {"entity": entity, **asdict(report)}
    (out_dir / "citations.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-active pytest tests/unit/test_note_outputs.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ariadne/report/ tests/unit/test_note_outputs.py
git commit -m "feat(report): persist note, provenance ledger, and citation report"
```

---

## Task 6: Neo4j stdio-config builder

**Files:**
- Create: `src/ariadne/graph/__init__.py`
- Create: `src/ariadne/graph/neo4j_server.py`
- Test: `tests/unit/test_neo4j_server_config.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_neo4j_server_config.py`:
```python
from __future__ import annotations

from ariadne.graph.neo4j_server import GRAPH_TOOLS, neo4j_stdio_config


def test_config_defaults_to_read_only_and_stdio() -> None:
    cfg = neo4j_stdio_config(env={})
    assert cfg["type"] == "stdio"
    assert cfg["command"] == "uvx"
    assert "--transport" in cfg["args"] and "stdio" in cfg["args"]
    assert cfg["env"]["NEO4J_READ_ONLY"] == "true"
    assert cfg["env"]["NEO4J_URI"] == "bolt://localhost:7687"


def test_config_reads_connection_from_env() -> None:
    cfg = neo4j_stdio_config(
        env={
            "NEO4J_URI": "bolt://db:7687",
            "NEO4J_USERNAME": "reader",
            "NEO4J_PASSWORD": "secret",
            "NEO4J_DATABASE": "intel",
        }
    )
    assert cfg["env"]["NEO4J_URI"] == "bolt://db:7687"
    assert cfg["env"]["NEO4J_USERNAME"] == "reader"
    assert cfg["env"]["NEO4J_PASSWORD"] == "secret"
    assert cfg["env"]["NEO4J_DATABASE"] == "intel"


def test_graph_tools_are_read_only() -> None:
    assert "mcp__neo4j__read_neo4j_cypher" in GRAPH_TOOLS
    assert "mcp__neo4j__get_neo4j_schema" in GRAPH_TOOLS
    assert all("write" not in t for t in GRAPH_TOOLS)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-active pytest tests/unit/test_neo4j_server_config.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ariadne.graph'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/ariadne/graph/__init__.py`:
```python
"""Graph connector — config for the read-only Neo4j MCP server."""
```

Create `src/ariadne/graph/neo4j_server.py`:
```python
"""Build the stdio config for the official ``mcp-neo4j-cypher`` server.

We expose Neo4j as a read-only MCP tool family. The server provides schema
introspection, query timeouts, and token-aware truncation — the governance
guardrails the brief requires — so we never hand-roll Cypher execution.
"""

from __future__ import annotations

from typing import Any

# Server pinned in pyproject; launched on demand via uvx for a clean subprocess.
_SERVER_SPEC = "mcp-neo4j-cypher@0.6.0"

# Read-only tool family the agent is allowed to call (write tool excluded entirely).
GRAPH_TOOLS = [
    "mcp__neo4j__get_neo4j_schema",
    "mcp__neo4j__read_neo4j_cypher",
]


def neo4j_stdio_config(env: dict[str, str]) -> dict[str, Any]:
    """Return an McpStdioServerConfig dict for the read-only Neo4j MCP server.

    ``env`` is typically ``os.environ``. Connection settings fall back to the
    server's local defaults; ``NEO4J_READ_ONLY`` is forced on.
    """
    server_env = {
        "NEO4J_URI": env.get("NEO4J_URI", "bolt://localhost:7687"),
        "NEO4J_USERNAME": env.get("NEO4J_USERNAME", "neo4j"),
        "NEO4J_PASSWORD": env.get("NEO4J_PASSWORD", "password"),
        "NEO4J_DATABASE": env.get("NEO4J_DATABASE", "neo4j"),
        "NEO4J_READ_ONLY": "true",
        "NEO4J_READ_TIMEOUT": env.get("NEO4J_READ_TIMEOUT", "30"),
    }
    return {
        "type": "stdio",
        "command": "uvx",
        "args": [_SERVER_SPEC, "--transport", "stdio"],
        "env": server_env,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-active pytest tests/unit/test_neo4j_server_config.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ariadne/graph/ tests/unit/test_neo4j_server_config.py
git commit -m "feat(graph): build read-only Neo4j stdio MCP config"
```

---

## Task 7: entity-workup skill

**Files:**
- Create: `.claude/skills/entity-workup/SKILL.md`
- Create: `.claude/skills/entity-workup/note-template.md`
- Test: `tests/unit/test_skill_frontmatter.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_skill_frontmatter.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-active pytest tests/unit/test_skill_frontmatter.py -q`
Expected: FAIL — `FileNotFoundError: .claude/skills/entity-workup/SKILL.md`.

- [ ] **Step 3: Write the skill and template**

Create `.claude/skills/entity-workup/SKILL.md`:
```markdown
---
name: entity-workup
description: Run an entity workup — given a target entity or organizational node, traverse its relationships in the Neo4j graph and produce a cited analytic note. Triggers on "run entity workup on …", "work up <entity>", "analyze entity …".
---

# Entity workup

You are an intelligence analyst's harness. Given a **target entity or
organizational node**, produce a concise, **fully cited** analytic note using
only the read-only graph tools `mcp__neo4j__get_neo4j_schema` and
`mcp__neo4j__read_neo4j_cypher`. Never assert a fact you did not retrieve.

## Loop: gather → act → verify → synthesize

1. **Gather.** Call `get_neo4j_schema` to learn node labels, relationship types,
   and properties. Locate the target with a read-only Cypher query (match by
   name/id). If absent, say so and stop.
2. **Act.** Write targeted read-only Cypher to expand the entity's
   neighborhood: direct relationships, the `REPORTS_TO` chain up and down,
   co-location and communication links. Prefer several focused queries over one
   giant query. Use parameters where possible.
3. **Verify.** Re-query to confirm any surprising or decisive link before you
   rely on it. Look specifically for **non-obvious, multi-hop** connections
   (paths of length ≥ 3) the analyst would miss by manual pivoting.
4. **Synthesize.** Write the note from `note-template.md`.

## Citation rule (mandatory)

After each graph query, the system records it and returns a provenance id of the
form `gN`. **Cite every asserted fact** with `[cite:gN]` for the query that
sourced it. If you did not receive an id for a claim, you may not assert it. If
the system did not surface ids, cite your graph queries in the order you ran
them: the first query is `g1`, the second `g2`, and so on. A note with an
uncited claim, or a `[cite:gN]` for a query you never ran, fails validation.

## Output

Output **only** the finished analytic note (Markdown), no preamble.
```

Create `.claude/skills/entity-workup/note-template.md`:
```markdown
# Analytic note: {{ENTITY}}

## Summary
2–4 sentences: who/what the entity is and the single most decisive finding. Cite each claim, e.g. `[cite:g1]`.

## Organizational position
Where the entity sits in the hierarchy — reports-to chain, units, roles. Cite each. `[cite:gN]`

## Relationships & connections
Key links (co-location, communication, membership). Call out any **non-obvious multi-hop connection** explicitly and trace the path. Cite each. `[cite:gN]`

## Gaps & caveats
What the graph does not show; ambiguity or missing links. (Citations optional here.)

## Provenance
Bullet list mapping each `gN` id used above to the Cypher query that produced it.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-active pytest tests/unit/test_skill_frontmatter.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/entity-workup/ tests/unit/test_skill_frontmatter.py
git commit -m "feat(skill): add entity-workup skill and note template"
```

---

## Task 8: CLI — arg parsing, options assembly, run loop

**Files:**
- Create: `src/ariadne/cli.py`
- Modify: `src/ariadne/__main__.py`
- Test: `tests/unit/test_cli_args.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_cli_args.py`:
```python
from __future__ import annotations

import pytest

from ariadne.cli import build_options, main, parse_args
from ariadne.graph.neo4j_server import GRAPH_TOOLS
from ariadne.provenance.ledger import ProvenanceLedger


def test_parse_args_defaults() -> None:
    ns = parse_args(["workup", "Alpha"])
    assert ns.command == "workup"
    assert ns.entity == "Alpha"
    assert ns.graph == "neo4j"
    assert ns.out == "./workups"


def test_parse_args_overrides() -> None:
    ns = parse_args(["workup", "Unit-7", "--out", "/tmp/x", "--format", "json"])
    assert ns.entity == "Unit-7"
    assert ns.out == "/tmp/x"
    assert ns.format == "json"


def test_build_options_wires_graph_server_and_hook() -> None:
    led = ProvenanceLedger()
    opts = build_options(ledger=led, env={"NEO4J_URI": "bolt://x:7687"})
    assert "neo4j" in opts.mcp_servers
    assert opts.mcp_servers["neo4j"]["env"]["NEO4J_READ_ONLY"] == "true"
    assert set(GRAPH_TOOLS).issubset(set(opts.allowed_tools))
    assert "PostToolUse" in opts.hooks


def test_main_without_api_key_exits_nonzero(monkeypatch, capsys) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rc = main(["workup", "Alpha"])
    assert rc != 0
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-active pytest tests/unit/test_cli_args.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ariadne.cli'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/ariadne/cli.py`:
```python
"""Ariadne CLI — `ariadne workup <entity>` runs the live agent loop.

Assembles ClaudeAgentOptions (read-only Neo4j MCP server + PostToolUse provenance
hook + entity-workup skill), runs the agent, validates citations, and persists the
note + ledger + citation report.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    HookMatcher,
    ResultMessage,
    TextBlock,
    query,
)

from ariadne.graph.neo4j_server import GRAPH_TOOLS, neo4j_stdio_config
from ariadne.provenance.citations import validate_citations
from ariadne.provenance.hook import make_provenance_hook
from ariadne.provenance.ledger import ProvenanceLedger
from ariadne.report.note import write_outputs

_SYSTEM_PROMPT = (
    "You are Ariadne, a sensemaking harness for intelligence analysts. Use only "
    "the read-only graph tools to gather evidence, and follow the entity-workup "
    "skill. Cite every fact as [cite:gN]. Output only the finished analytic note."
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ariadne")
    sub = parser.add_subparsers(dest="command", required=True)
    wk = sub.add_parser("workup", help="Work up a target entity or org node")
    wk.add_argument("entity", help="Target entity or organizational node")
    wk.add_argument("--graph", default="neo4j", choices=["neo4j"], help="Graph backend")
    wk.add_argument("--out", default="./workups", help="Output directory root")
    wk.add_argument("--format", default="md", choices=["md", "json"], help="Console format")
    return parser.parse_args(argv)


def build_options(*, ledger: ProvenanceLedger, env: dict[str, str]) -> ClaudeAgentOptions:
    hook = make_provenance_hook(ledger)
    return ClaudeAgentOptions(
        mcp_servers={"neo4j": neo4j_stdio_config(env)},
        allowed_tools=list(GRAPH_TOOLS),
        system_prompt=_SYSTEM_PROMPT,
        permission_mode="default",
        setting_sources=["project"],  # discover .claude/skills/entity-workup
        hooks={"PostToolUse": [HookMatcher(matcher="mcp__neo4j__.*", hooks=[hook])]},
    )


async def run_workup(entity: str, out_root: str, env: dict[str, str]) -> int:
    ledger = ProvenanceLedger()
    options = build_options(ledger=ledger, env=env)
    prompt = f"Run entity workup on: {entity}"

    note_parts: list[str] = []
    result_text: str | None = None
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    note_parts.append(block.text)
        elif isinstance(message, ResultMessage):
            result_text = message.result

    note = (result_text or "\n".join(note_parts)).strip()
    report = validate_citations(note, ledger)
    out_dir = Path(out_root) / _slug(entity)
    write_outputs(out_dir, entity=entity, note=note, ledger=ledger, report=report)

    print(f"Wrote {out_dir}/note.md ({len(ledger.entries)} graph calls cited).")
    if not report.ok:
        print(f"Citation check FAILED — dangling: {report.dangling}", file=sys.stderr)
        return 1
    return 0


def _slug(entity: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in entity).strip("-").lower() or "entity"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.command != "workup":
        print("unknown command", file=sys.stderr)
        return 2
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "ANTHROPIC_API_KEY is not set — export it to run the live agent loop.",
            file=sys.stderr,
        )
        return 2
    return asyncio.run(run_workup(args.entity, args.out, dict(os.environ)))
```

Replace the body of `src/ariadne/__main__.py` with:
```python
"""Command-line entrypoint for Ariadne."""

from __future__ import annotations

from ariadne.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-active pytest tests/unit/test_cli_args.py -q`
Expected: PASS (4 passed). If `build_options` fails on the `HookMatcher(...)` form, switch to the dict form discovered in Task 1 Step 3.

- [ ] **Step 5: Fix the obsolete smoke test**

`tests/test_smoke.py::test_cli_default_runs` calls `main([])`, which now requires a subcommand. Replace its body:
```python
def test_cli_requires_subcommand() -> None:
    import pytest

    with pytest.raises(SystemExit):
        main([])
```
Remove `test_cli_version_flag` (the scaffold `--version` flag is gone). Keep `test_version_is_set`.

- [ ] **Step 6: Run the full unit suite + lint**

Run: `uv run --no-active pytest -m "not integration and not slow" -q && uv run --no-active ruff check . && uv run --no-active ty check`
Expected: all unit tests pass; ruff and ty clean.

- [ ] **Step 7: Commit**

```bash
git add src/ariadne/cli.py src/ariadne/__main__.py tests/unit/test_cli_args.py tests/test_smoke.py
git commit -m "feat(cli): add workup command running the live agent loop with provenance"
```

---

## Task 9: Neo4j infra and synthetic seed data

**Files:**
- Create: `infra/neo4j/docker-compose.yml`
- Create: `infra/neo4j/seed.cypher`

- [ ] **Step 1: Write the compose file**

Create `infra/neo4j/docker-compose.yml`:
```yaml
services:
  neo4j:
    image: neo4j:5.26-community
    container_name: ariadne-neo4j
    ports:
      - "7474:7474"   # browser
      - "7687:7687"   # bolt
    environment:
      NEO4J_AUTH: neo4j/ariadnedev
      NEO4J_server_memory_pagecache_size: 256M
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:7474 || exit 1"]
      interval: 5s
      timeout: 5s
      retries: 20
```

- [ ] **Step 2: Write the synthetic seed graph**

Create `infra/neo4j/seed.cypher` — a fictional org hierarchy with one deliberately non-obvious 3-hop link (Halberd and Wren are connected only via a co-located unit high in the hierarchy):
```cypher
// Ariadne synthetic org-hierarchy seed. Fictional. No real-world entities.
MATCH (n) DETACH DELETE n;

CREATE (hq:Unit {name: 'Directorate-HQ', echelon: 1});
CREATE (ops:Unit {name: 'Operations-Wing', echelon: 2});
CREATE (sig:Unit {name: 'Signals-Cell', echelon: 3});
CREATE (log:Unit {name: 'Logistics-Cell', echelon: 3});
CREATE (site:Site {name: 'Compound-Alpha'});

CREATE (halberd:Person {name: 'Halberd', alias: 'H1'});
CREATE (wren:Person {name: 'Wren', alias: 'W4'});
CREATE (talon:Person {name: 'Talon', alias: 'T2'});
CREATE (osprey:Person {name: 'Osprey', alias: 'O7'});

// Hierarchy
MATCH (ops:Unit {name:'Operations-Wing'}), (hq:Unit {name:'Directorate-HQ'})
CREATE (ops)-[:REPORTS_TO]->(hq);
MATCH (sig:Unit {name:'Signals-Cell'}), (ops:Unit {name:'Operations-Wing'})
CREATE (sig)-[:REPORTS_TO]->(ops);
MATCH (log:Unit {name:'Logistics-Cell'}), (ops:Unit {name:'Operations-Wing'})
CREATE (log)-[:REPORTS_TO]->(ops);

// Membership
MATCH (halberd:Person {name:'Halberd'}), (sig:Unit {name:'Signals-Cell'})
CREATE (halberd)-[:MEMBER_OF {role:'Lead'}]->(sig);
MATCH (talon:Person {name:'Talon'}), (sig:Unit {name:'Signals-Cell'})
CREATE (talon)-[:MEMBER_OF {role:'Analyst'}]->(sig);
MATCH (wren:Person {name:'Wren'}), (log:Unit {name:'Logistics-Cell'})
CREATE (wren)-[:MEMBER_OF {role:'Lead'}]->(log);
MATCH (osprey:Person {name:'Osprey'}), (log:Unit {name:'Logistics-Cell'})
CREATE (osprey)-[:MEMBER_OF {role:'Driver'}]->(log);

// Direct communication (obvious links)
MATCH (halberd:Person {name:'Halberd'}), (talon:Person {name:'Talon'})
CREATE (halberd)-[:COMMUNICATES_WITH {channel:'voice'}]->(talon);

// Non-obvious link: Halberd and Wren never talk directly, but both units are
// co-located at Compound-Alpha — a 3-hop CO_LOCATED path the analyst would miss.
MATCH (sig:Unit {name:'Signals-Cell'}), (site:Site {name:'Compound-Alpha'})
CREATE (sig)-[:CO_LOCATED]->(site);
MATCH (log:Unit {name:'Logistics-Cell'}), (site:Site {name:'Compound-Alpha'})
CREATE (log)-[:CO_LOCATED]->(site);
```

- [ ] **Step 3: Smoke-test the seed against a real container (manual, one-off)**

Run:
```bash
docker compose -f infra/neo4j/docker-compose.yml up -d
# wait for healthy, then load the seed:
uv run --no-active python -c "
from neo4j import GraphDatabase
import pathlib, time
for _ in range(30):
    try:
        d=GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','ariadnedev')); d.verify_connectivity(); break
    except Exception: time.sleep(2)
stmts=[s.strip() for s in pathlib.Path('infra/neo4j/seed.cypher').read_text().split(';') if s.strip() and not s.strip().startswith('//')]
with d.session() as s:
    for st in stmts: s.run(st)
    n=s.run('MATCH (n) RETURN count(n) AS c').single()['c']
print('nodes:', n)
"
docker compose -f infra/neo4j/docker-compose.yml down
```
Expected: prints `nodes: 9` (5 units/site + 4 persons). If a statement errors, fix `seed.cypher`.

- [ ] **Step 4: Commit**

```bash
git add infra/neo4j/
git commit -m "feat(infra): add Neo4j compose service and synthetic org-graph seed"
```

---

## Task 10: Integration test — live end-to-end (key-gated)

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/conftest.py`
- Create: `tests/integration/test_workup_e2e.py`

- [ ] **Step 1: Write the Neo4j container fixture**

Create `tests/integration/__init__.py` (empty) and `tests/integration/conftest.py`:
```python
from __future__ import annotations

import pathlib

import pytest

pytest.importorskip("testcontainers")
from testcontainers.neo4j import Neo4jContainer  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

SEED = pathlib.Path("infra/neo4j/seed.cypher")


@pytest.fixture(scope="session")
def neo4j_url() -> str:
    with Neo4jContainer("neo4j:5.26-community") as neo:
        url = neo.get_connection_url()  # bolt://host:port
        password = neo.password
        driver = GraphDatabase.driver(url, auth=("neo4j", password))
        stmts = [
            s.strip()
            for s in SEED.read_text().split(";")
            if s.strip() and not s.strip().startswith("//")
        ]
        with driver.session() as session:
            for st in stmts:
                session.run(st)
        driver.close()
        # expose creds to the workup via env in the test
        yield url
```

- [ ] **Step 2: Write the end-to-end test**

Create `tests/integration/test_workup_e2e.py`:
```python
from __future__ import annotations

import json
import os
from urllib.parse import urlparse

import pytest

from ariadne.cli import run_workup

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_live_workup_produces_cited_note(neo4j_url, tmp_path) -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("no ANTHROPIC_API_KEY — live agent run skipped")

    parsed = urlparse(neo4j_url)
    env = {
        **os.environ,
        "NEO4J_URI": neo4j_url,
        "NEO4J_USERNAME": "neo4j",
        "NEO4J_PASSWORD": "test",  # testcontainers default; adjust if fixture differs
    }
    rc = await run_workup("Halberd", str(tmp_path), env)

    out = tmp_path / "halberd"
    note = (out / "note.md").read_text()
    citations = json.loads((out / "citations.json").read_text())

    assert rc == 0
    assert citations["ok"] is True
    assert citations["cited"], "note must cite at least one graph call"
    assert (out / "provenance.jsonl").read_text().strip()
    # success criterion (4): surfaces the planted non-obvious link
    assert "Compound-Alpha" in note or "co-located" in note.lower()
```

- [ ] **Step 3: Run the integration test**

Run: `uv run --no-active pytest -m integration -q`
Expected: with Docker running and a key set — PASS. Without a key — the test SKIPS (container still starts). If `neo4j_url` auth differs from the test's assumed creds, align the password in both the fixture `yield` and the test `env` (read `neo.password`/`get_connection_url` from the fixture; thread the password through the fixture return if needed).

- [ ] **Step 4: Commit**

```bash
git add tests/integration/
git commit -m "test(integration): live workup e2e against seeded Neo4j (key-gated)"
```

---

## Task 11: Wire docs, roadmap, and final gates

**Files:**
- Modify: `README.md`, `ROADMAP.md`, `IMPL.md`, `.claude/skill-context.md`

- [ ] **Step 1: Update ROADMAP — mark Phase 1 items shipped**

In `ROADMAP.md`, check off the Phase 1 checkboxes and add a `Shipped` line dated today:
```markdown
- **2026-06-01** — Phase 1 vertical slice: read-only Neo4j MCP connector,
  entity-workup skill, PostToolUse provenance hook + citation validator, and
  `ariadne workup <entity>` CLI producing a cited analytic note.
```

- [ ] **Step 2: Update IMPL — replace the Phase-0 pickup with Phase-1 status**

In `IMPL.md`, move the "freeze Phase-1 scope" block to done and note the live slice landed; point next work at Phase 2 (SQL + vector connectors, source-routing).

- [ ] **Step 3: Update README — add a usage section**

Add to `README.md` a short "Quickstart" showing:
```bash
docker compose -f infra/neo4j/docker-compose.yml up -d   # start Neo4j
# seed it (see infra/neo4j/seed.cypher)
export ANTHROPIC_API_KEY=...                              # required for the agent loop
uv run ariadne workup Halberd --out ./workups             # -> ./workups/halberd/note.md
```

- [ ] **Step 4: Update `.claude/skill-context.md`**

Change the `has:` line — Docker is now used (Neo4j compose), the CLI is `ariadne workup <entity>`, and runtime deps are no longer empty.

- [ ] **Step 5: Run the full pre-push gate**

Run: `uv run --no-active ruff format --check . && uv run --no-active ruff check . && uv run --no-active ty check && uv run --no-active pytest -m "not integration and not slow" -q`
Expected: all clean and green.

- [ ] **Step 6: Commit**

```bash
git add README.md ROADMAP.md IMPL.md .claude/skill-context.md
git commit -m "docs: record Phase 1 vertical slice as shipped; add quickstart"
```

---

## Self-review notes (author)

- **Spec coverage:** connector (T6), skill (T7), provenance hook (T3), CLI/cited note (T8), Neo4j + seed (T9), citation contract/validator (T4), deps (T1), tests unit+integration (T2–T10), error handling (T8 main + T8 run_workup), success criteria (T10). All spec sections map to a task.
- **API risk:** the `HookMatcher` shape and `PostToolUse` `additionalContext` support are the only fast-moving unknowns; T1.S3 verifies them and T3.S5 documents the no-additionalContext fallback. The deterministic units never depend on either.
- **Type consistency:** `ProvenanceLedger.record/has/entries/write_jsonl`, `CitationReport(ok,cited,dangling,unused)`, `validate_citations`, `make_provenance_hook`, `neo4j_stdio_config`/`GRAPH_TOOLS`, `write_outputs`, `build_options`/`parse_args`/`run_workup`/`main` are used consistently across tasks.
```
