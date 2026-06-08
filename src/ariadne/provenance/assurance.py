"""Unified governance/assurance verdict — folds the four signals into one.

The brief requires governance uniform across **quality, security, and data
integrity**. Four signals already cover those axes separately: the read-only
audit (security), the citation gate (sourcing quality), the ICD-203 tradecraft
lint (calibration quality), and the egress posture (data integrity / isolation).
Each is sound on its own but reaches the analyst as a scattered set of JSON
artifacts and dashboard cards. :func:`build_verdict` aggregates them into one
:class:`GovernanceVerdict` — the single analyst-facing "is this product
trustworthy?" answer.

The aggregation is **weakest-link, never averaged**. A composite single number
would let a strong analytic-quality score mask a safety-gate breach, so:

- a **hard** axis (read-only, citations) failing makes the whole verdict ``FAIL``;
- an **advisory** axis (tradecraft) with a finding makes it ``ADVISORY`` — never
  ``FAIL`` (calibration is improvable, not a contract breach);
- the **posture** axis (egress) is descriptive — it reports the configured
  isolation mode and never moves the status (per-run, there is no runtime egress
  gate; enforcement is the air-gapped CI guard, ADR-0033).

# research(2026-06): composite single-number assurance scores are misleading;
# weakest-link gating over distinct safety vs quality dimensions is the 2026
# standard (Kili "AI Benchmarks 2026"; "Evaluating Frontier Safety Frameworks"
# arXiv:2512.01166 — assurance is the weakest treated dimension, so it must not
# be averaged away). The multi-axis "model-card / nutrition-label" presentation
# (separate sections, not one score) is the transparency convention (AI model
# cards, 2026). Maps to the brief's quality/security/data-integrity triad.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ariadne.provenance.citations import CitationReport, CoverageStats
    from ariadne.provenance.governance import GovernanceReport
    from ariadne.provenance.tradecraft import TradecraftReport

# Axis tiers — how an axis participates in the overall status.
HARD = "hard"  # a failure fails the whole verdict (a contract breach)
ADVISORY = "advisory"  # tier AND status: a finding marks the verdict advisory
POSTURE = "posture"  # descriptive only; never moves the status

# Overall verdict statuses (weakest-link, never an averaged score). ADVISORY is
# reused — the advisory tier and the advisory status are the same literal.
PASS = "pass"  # noqa: S105 — an analytic verdict status, not a credential
FAIL = "fail"


@dataclass(frozen=True)
class AssuranceAxis:
    """One governance dimension in the folded verdict (a model-card section)."""

    key: str  # stable id: read_only | citations | tradecraft | egress
    label: str  # human-facing axis name
    pillar: str  # brief's triad: security | quality | data-integrity
    tier: str  # HARD | ADVISORY | POSTURE
    status: str  # PASS | FAIL | ADVISORY, or the posture string for POSTURE axes
    detail: str  # one-line analyst-facing summary


@dataclass(frozen=True)
class GovernanceVerdict:
    """The folded, weakest-link governance verdict over the four axes."""

    axes: list[AssuranceAxis] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True iff every hard gate passes — the single gateable boolean."""
        return not any(a.tier == HARD and a.status == FAIL for a in self.axes)

    @property
    def status(self) -> str:
        """Weakest-link overall status: FAIL > ADVISORY > PASS, never averaged."""
        if not self.ok:
            return FAIL
        if any(a.tier == ADVISORY and a.status == ADVISORY for a in self.axes):
            return ADVISORY
        return PASS

    def to_payload(self) -> dict:
        """JSON-serializable verdict: status + ok + the per-axis model-card sections.

        The computed ``status``/``ok`` are persisted alongside the axes so a reader
        (report, CLI) renders the verdict without re-deriving the weakest-link rule.
        """
        return {
            "status": self.status,
            "ok": self.ok,
            "axes": [asdict(a) for a in self.axes],
        }


def build_verdict(
    *,
    governance: GovernanceReport,
    citations: CitationReport,
    coverage: CoverageStats | None,
    tradecraft: TradecraftReport,
    egress: str,
) -> GovernanceVerdict:
    """Fold the four governance signals into one weakest-link verdict."""
    return GovernanceVerdict(
        axes=[
            _read_only_axis(governance),
            _citations_axis(citations, coverage),
            _tradecraft_axis(tradecraft),
            _egress_axis(egress),
        ]
    )


def _read_only_axis(governance: GovernanceReport) -> AssuranceAxis:
    n = len(governance.write_attempts)
    return AssuranceAxis(
        key="read_only",
        label="Read-only contract",
        pillar="security",
        tier=HARD,
        status=PASS if governance.ok else FAIL,
        detail=("read-only upheld" if governance.ok else f"{n} write attempt(s) in the ledger"),
    )


def _citations_axis(citations: CitationReport, coverage: CoverageStats | None) -> AssuranceAxis:
    if coverage is None:
        pct = "coverage n/a"  # not recorded for this run (≠ zero citable claims)
    elif coverage.fraction is None:
        pct = "no citable claims"  # genuinely empty: nothing to cite
    else:
        pct = f"{round(coverage.fraction * 100)}% coverage"
    if citations.ok:
        detail = f"every claim grounded · {pct}"
    else:
        n_uncited = len(citations.uncited)
        n_dangling = len(citations.dangling)
        detail = f"{n_uncited} uncited · {n_dangling} dangling · {pct}"
    return AssuranceAxis(
        key="citations",
        label="Citation gate",
        pillar="quality",
        tier=HARD,
        status=PASS if citations.ok else FAIL,
        detail=detail,
    )


def _tradecraft_axis(tradecraft: TradecraftReport) -> AssuranceAxis:
    n_nonstandard = len(tradecraft.nonstandard_terms)
    has_finding = n_nonstandard > 0 or not tradecraft.has_confidence_statement
    if not has_finding:
        detail = f"{len(tradecraft.standard_terms)} ICD-203 term(s) · confidence stated"
    else:
        bits = []
        if n_nonstandard:
            bits.append(f"{n_nonstandard} non-standard hedge(s)")
        if not tradecraft.has_confidence_statement:
            bits.append("no confidence statement")
        detail = " · ".join(bits)
    return AssuranceAxis(
        key="tradecraft",
        label="ICD-203 tradecraft",
        pillar="quality",
        tier=ADVISORY,
        status=ADVISORY if has_finding else PASS,
        detail=detail,
    )


def _egress_axis(egress: str) -> AssuranceAxis:
    return AssuranceAxis(
        key="egress",
        label="Egress posture",
        pillar="data-integrity",
        tier=POSTURE,
        status=egress,
        detail=f"isolation posture: {egress}",
    )
