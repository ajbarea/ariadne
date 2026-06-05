"""Context utilization — of the evidence retrieved, what fraction grounded a cited claim.

ADR-0019: a deterministic, descriptive retrieval-side signal for an agentic
sensemaking workup. RAGAS-style precision@k does not apply — Ariadne retrieves by a
sequence of tool calls, not a ranked single-pass lookup — so this measures the SoK's
"context utilization" axis instead: did the retrieved evidence actually influence the
analysis? It is **reported, never gated**: exploratory and negative-confirmation
retrieval (ACH, establishing an absence) legitimately lowers it.

# research(2026-06): SoK Agentic RAG (arXiv 2603.07379) trajectory-aware retrieval
# eval — context utilization, not precision@k. See ADR-0019.
"""

from __future__ import annotations

import re

_CITE_RE = re.compile(r"\[cite:(g\d+)\]")


def context_utilization(note: str, ledger_entries: list[dict]) -> float | None:
    """Fraction of distinct retrieved evidence (``gN``) that is cited in the note.

    ``None`` when nothing was retrieved (no denominator — distinct from ``0.0``,
    which would read as "all noise"). The numerator counts only retrieved evidence
    that is also cited, so a dangling citation (cited but never retrieved) is a
    citation error, not utilization, and is excluded.
    """
    retrieved = {str(e.get("id")) for e in ledger_entries if e.get("id")}
    if not retrieved:
        return None
    cited = set(_CITE_RE.findall(note))
    return len(retrieved & cited) / len(retrieved)
