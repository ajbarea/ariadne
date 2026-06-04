"""The workup exit-code policy: how --strict, governance, citations, and agent
errors combine into a process exit code.

A read-only contract breach is the security/data-integrity axis (exit 3) and,
under --strict, takes precedence over the analytic-quality failures (exit 1) —
a mutated evidence store taints the whole product. Default (non-strict) is
non-breaking: a breach is advisory only.
"""

from __future__ import annotations

from ariadne.cli import workup_exit_code
from ariadne.provenance.governance import GovernanceReport

_OK = GovernanceReport(ok=True)
_VIOLATION = GovernanceReport(
    ok=False, write_attempts=[{"id": "g1", "verb": "CREATE", "statement": "CREATE (n)"}]
)


def test_clean_run_exits_zero() -> None:
    assert workup_exit_code(governance=_OK, strict=False, had_error=False, citations_ok=True) == 0


def test_violation_without_strict_is_advisory_only() -> None:
    assert (
        workup_exit_code(governance=_VIOLATION, strict=False, had_error=False, citations_ok=True)
        == 0
    )


def test_violation_with_strict_exits_three() -> None:
    assert (
        workup_exit_code(governance=_VIOLATION, strict=True, had_error=False, citations_ok=True)
        == 3
    )


def test_strict_violation_takes_precedence_over_citation_failure() -> None:
    assert (
        workup_exit_code(governance=_VIOLATION, strict=True, had_error=False, citations_ok=False)
        == 3
    )


def test_strict_violation_takes_precedence_over_agent_error() -> None:
    assert (
        workup_exit_code(governance=_VIOLATION, strict=True, had_error=True, citations_ok=True) == 3
    )


def test_agent_error_exits_one() -> None:
    assert workup_exit_code(governance=_OK, strict=False, had_error=True, citations_ok=True) == 1


def test_citation_failure_exits_one() -> None:
    assert workup_exit_code(governance=_OK, strict=False, had_error=False, citations_ok=False) == 1
