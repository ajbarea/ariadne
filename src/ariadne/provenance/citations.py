"""Citation extraction and coverage validation.

The analytic note cites graph facts as ``[cite:gN]``. A note PASSES validation
only if every citation resolves to a ledger entry (no fabricated sources). This
is Ariadne's first concrete answer to "how do you know it works?".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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
    """Validate that all citations in a note resolve to ledger entries."""
    cited = extract_citations(note)
    ledger_ids = [e["id"] for e in ledger.entries]
    dangling = [c for c in cited if not ledger.has(c)]
    unused = [i for i in ledger_ids if i not in cited]
    return CitationReport(ok=not dangling, cited=cited, dangling=dangling, unused=unused)
