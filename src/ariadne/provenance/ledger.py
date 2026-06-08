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
        full = str(response)
        entry: dict[str, Any] = {
            "id": cite_id,
            "ts": datetime.now(UTC).isoformat(),
            "tool": tool,
            "tool_input": tool_input,
            "response_excerpt": full[: self._excerpt_chars],
        }
        # Record the original length only when truncated, so the report can warn the
        # analyst that the evidence they're verifying against is partial.
        if len(full) > self._excerpt_chars:
            entry["response_full_len"] = len(full)
        self._entries.append(entry)
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

    @staticmethod
    def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
        """Load the entries written by ``write_jsonl`` (skips blank lines)."""
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]
