"""Shared run model + trajectory structural extraction for Axis B (ADR-0029/0030).

The bits B2 (`distil`) and B3 (`reflect`) both need: load a run's persisted artifacts into
a :class:`RunArtifacts`, and categorize the trajectory by tool family / phase. Neither reads
the fixture gold — only the run's own artifacts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ariadne.provenance.ledger import ProvenanceLedger

# MCP server name -> the capability it provides.
_CAPABILITY = {"neo4j": "graph", "postgres": "relational", "ariadne": "semantic"}


@dataclass(frozen=True)
class RunArtifacts:
    """One immutable run dir's persisted artifacts (ADR-0021), as Axis B reads them."""

    run_dir: str
    provenance: list[dict[str, Any]]
    eval_scores: dict[str, Any]
    manifest: dict[str, Any] | None
    note: str
    citations: dict[str, Any] | None = None
    governance: dict[str, Any] | None = None


def _read_json(path: Path) -> dict[str, Any] | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def load_run(run_dir: str | Path) -> RunArtifacts:
    """Load a run's trajectory, scores, manifest, note, citations, governance.

    Missing files degrade to ``{}`` / ``None`` / ``""`` — ``load_run`` never refuses a run
    (a fixture-less live workup has no ``eval.json``); the per-command gate, not the loader,
    is what rejects an ineligible run.
    """
    run_dir = Path(run_dir)
    prov = run_dir / "provenance.jsonl"
    note = run_dir / "note.md"
    return RunArtifacts(
        run_dir=str(run_dir),
        provenance=ProvenanceLedger.read_jsonl(prov) if prov.is_file() else [],
        eval_scores=_read_json(run_dir / "eval.json") or {},
        manifest=_read_json(run_dir / "manifest.json"),
        note=note.read_text(encoding="utf-8") if note.is_file() else "",
        citations=_read_json(run_dir / "citations.json"),
        governance=_read_json(run_dir / "governance.json"),
    )


def skills_invoked(run: RunArtifacts) -> set[str] | None:
    """The skill names a run recorded as invoked, or ``None`` if no signal was recorded.

    ``None`` (the manifest has no ``skills_invoked`` key) means the instrument is absent — a legacy
    run, or recording not yet wired (ADR-0034) — and is deliberately distinct from an empty set
    (recorded, none fired). The invocation gate treats ``None`` as *unobserved* (a caveat, never a
    false reject) and a non-matching set as *not invoked* (the confound SkillTester guards against).
    """
    if not run.manifest:
        return None
    raw = run.manifest.get("skills_invoked")
    return None if raw is None else set(raw)


def tool_family(tool: str) -> str:
    """The MCP server a tool belongs to: ``mcp__<server>__<name>`` -> ``<server>``."""
    parts = tool.split("__")
    return parts[1] if len(parts) >= 3 and parts[0] == "mcp" else "other"


def prerequisites(run: RunArtifacts) -> tuple[str, ...]:
    """The distinct, sorted capabilities (graph / relational / semantic) the run used."""
    caps = {_CAPABILITY.get(fam := tool_family(e.get("tool", "")), fam) for e in run.provenance}
    return tuple(sorted(caps))


def _is_graph_schema_query(query: str) -> bool:
    q = query.lower()
    return any(
        p in q for p in ("db.labels", "db.relationshiptypes", "db.schema", "db.propertykeys")
    )


def _is_fulltext_sql(sql: str) -> bool:
    s = sql.lower()
    return any(p in s for p in ("@@", "tsquery", "tsvector", "ts_rank"))


def phase_of(entry: dict[str, Any]) -> str:
    """Categorize one trajectory entry into an analytic phase by tool family + query shape."""
    tool = entry.get("tool", "")
    fam = tool_family(tool)
    ti = entry.get("tool_input", {}) or {}
    if fam == "neo4j":
        if "get_neo4j_schema" in tool or _is_graph_schema_query(ti.get("query") or ""):
            return "graph-schema"
        return "graph-traversal"
    if fam == "postgres":
        if not tool.endswith("execute_sql"):
            return "relational-schema"
        sql = ti.get("sql") or ti.get("query") or ""
        return "free-text" if _is_fulltext_sql(sql) else "relational-query"
    if fam == "ariadne":
        return "free-text"
    return "other"


def query_text(entry: dict[str, Any]) -> str:
    """The Cypher/SQL/search text an entry ran, or ``""``."""
    ti = entry.get("tool_input", {}) or {}
    return ti.get("query") or ti.get("sql") or ""


def truncate(text: str, limit: int) -> str:
    """Whitespace-collapse and clip ``text`` to ``limit`` chars with an ellipsis."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def fmt_score(value: Any) -> str:
    """Round a float for human prose (a persisted JSON/TOML record keeps full precision)."""
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def move_sequence(provenance: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """The trajectory collapsed into consecutive same-phase steps, in run order."""
    steps: list[tuple[str, list[dict[str, Any]]]] = []
    for entry in provenance:
        ph = phase_of(entry)
        if steps and steps[-1][0] == ph:
            steps[-1][1].append(entry)
        else:
            steps.append((ph, [entry]))
    return steps
