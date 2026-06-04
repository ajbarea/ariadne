"""Read-only governance audit over the provenance ledger.

The brief requires governance uniform across **quality, security, and data
integrity**. Quality is covered (citation gate, tradecraft lint, ICD-203 rubric).
This is the security / data-integrity axis: the analytic loop is read-only by
construction (Neo4j read-only, postgres-mcp restricted mode), and this audit
*verifies* it rather than trusting it — any mutating verb in a ledger statement
is a contract violation, including a write the agent attempted that the connector
blocked. Verifying the posture (not just configuring it) is the same
defence-in-depth the citation gate applies to sourcing.

# research(2026-06): defence-in-depth — audit the actual tool trace, do not
# assume the connector's read-only config was respected. See the brief's
# governance constraint and docs/research/analytic-rigor-eval.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ariadne.evaluation._text import statement_text

# Mutating verbs across both query languages (Cypher writes + SQL DML/DDL/DCL).
# Word-boundary matched, case-insensitive, so column names like ``created_at`` or
# ``subset_id`` do not false-positive.
_WRITE_VERBS = (
    "CREATE",
    "MERGE",
    "DELETE",
    "DETACH",
    "SET",
    "REMOVE",
    "INSERT",
    "UPDATE",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "GRANT",
    "REVOKE",
)
_WRITE_RE = re.compile(r"\b(" + "|".join(_WRITE_VERBS) + r")\b", re.IGNORECASE)


@dataclass(frozen=True)
class GovernanceReport:
    """Result of the read-only audit. ``ok`` is False if any write was attempted."""

    ok: bool
    write_attempts: list[dict] = field(default_factory=list)  # [{id, verb, statement}]


def audit_read_only(ledger_entries: list[dict]) -> GovernanceReport:
    """Flag any ledger statement carrying a mutating verb (read-only enforcement)."""
    attempts: list[dict] = []
    for entry in ledger_entries:
        statement = statement_text(entry)
        match = _WRITE_RE.search(statement)
        if match:
            attempts.append(
                {
                    "id": entry.get("id", ""),
                    "verb": match.group(1).upper(),
                    "statement": statement,
                }
            )
    return GovernanceReport(ok=not attempts, write_attempts=attempts)
