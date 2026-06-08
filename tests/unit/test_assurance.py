"""Hermetic tests for the unified governance/assurance verdict (ADR Phase 4 fold).

The brief requires governance uniform across **quality, security, and data
integrity**. Four signals already measure those axes separately — the read-only
audit (security), the citation gate (sourcing quality), the ICD-203 tradecraft
lint (calibration quality), and the egress posture (data-integrity / isolation).
This folds them into one analyst-facing verdict.

The aggregation is **weakest-link, never averaged**: a single composite number
would let a strong quality score mask a safety-gate failure. So the overall
status is FAIL if *any* hard gate fails, ADVISORY if only an advisory axis has a
finding, and PASS otherwise; the egress posture is descriptive and never moves
the status.

research(2026-06): composite single-number assurance scores are misleading;
weakest-link gating over distinct safety/quality dimensions is the 2026 standard
(Kili AI Benchmarks 2026; Frontier Safety Frameworks eval arXiv:2512.01166). The
multi-axis "model-card / nutrition-label" presentation (separate sections, not an
average) is the transparency convention (model-card practice 2026).
"""

from __future__ import annotations

from ariadne.provenance.assurance import (
    ADVISORY,
    FAIL,
    HARD,
    PASS,
    POSTURE,
    build_verdict,
)
from ariadne.provenance.citations import CitationReport, CoverageStats
from ariadne.provenance.governance import GovernanceReport
from ariadne.provenance.tradecraft import TradecraftReport


def _clean_citations() -> CitationReport:
    return CitationReport(ok=True, cited=["g1"], dangling=[], unused=[], uncited=[], unsupported=[])


def _clean_tradecraft() -> TradecraftReport:
    return TradecraftReport(
        standard_terms=[("likely", "55-80%")],
        nonstandard_terms=[],
        has_confidence_statement=True,
    )


def _full_coverage() -> CoverageStats:
    return CoverageStats(covered=4, total=4, fraction=1.0)


def test_all_axes_clean_is_pass() -> None:
    verdict = build_verdict(
        governance=GovernanceReport(ok=True),
        citations=_clean_citations(),
        coverage=_full_coverage(),
        tradecraft=_clean_tradecraft(),
        egress="enclave",
    )
    assert verdict.status == PASS
    assert verdict.ok is True


def test_read_only_violation_fails_the_whole_verdict() -> None:
    # A mutated evidence store taints the product regardless of analytic quality.
    verdict = build_verdict(
        governance=GovernanceReport(ok=False, write_attempts=[{"id": "g2", "verb": "DELETE"}]),
        citations=_clean_citations(),
        coverage=_full_coverage(),
        tradecraft=_clean_tradecraft(),
        egress="enclave",
    )
    assert verdict.status == FAIL
    assert verdict.ok is False


def test_citation_gate_failure_fails_the_verdict() -> None:
    verdict = build_verdict(
        governance=GovernanceReport(ok=True),
        citations=CitationReport(
            ok=False, cited=["g1"], dangling=["g9"], unused=[], uncited=["a claim"], unsupported=[]
        ),
        coverage=CoverageStats(covered=3, total=4, fraction=0.75),
        tradecraft=_clean_tradecraft(),
        egress="enclave",
    )
    assert verdict.status == FAIL
    assert verdict.ok is False


def test_tradecraft_finding_is_advisory_not_failure() -> None:
    # Non-standard estimative hedges are a calibration advisory, never a gate.
    verdict = build_verdict(
        governance=GovernanceReport(ok=True),
        citations=_clean_citations(),
        coverage=_full_coverage(),
        tradecraft=TradecraftReport(
            standard_terms=[], nonstandard_terms=["possibly"], has_confidence_statement=False
        ),
        egress="enclave",
    )
    assert verdict.status == ADVISORY
    assert verdict.ok is True  # advisories never fail the gate


def test_hard_failure_dominates_an_advisory() -> None:
    # Weakest-link: a hard breach outranks an advisory; status is FAIL, not ADVISORY.
    verdict = build_verdict(
        governance=GovernanceReport(ok=False, write_attempts=[{"id": "g2", "verb": "SET"}]),
        citations=_clean_citations(),
        coverage=_full_coverage(),
        tradecraft=TradecraftReport(
            standard_terms=[], nonstandard_terms=["maybe"], has_confidence_statement=False
        ),
        egress="enclave",
    )
    assert verdict.status == FAIL


def test_egress_posture_is_descriptive_and_never_changes_status() -> None:
    # "inherit" is a weaker isolation posture than "enclave", but the per-run
    # verdict only reports it — it is not a runtime gate, so it never fails.
    verdict = build_verdict(
        governance=GovernanceReport(ok=True),
        citations=_clean_citations(),
        coverage=_full_coverage(),
        tradecraft=_clean_tradecraft(),
        egress="inherit",
    )
    assert verdict.status == PASS
    egress_axis = next(a for a in verdict.axes if a.key == "egress")
    assert egress_axis.tier == POSTURE
    assert egress_axis.status == "inherit"


def test_axes_carry_tier_and_pillar_for_the_model_card_layout() -> None:
    verdict = build_verdict(
        governance=GovernanceReport(ok=True),
        citations=_clean_citations(),
        coverage=_full_coverage(),
        tradecraft=_clean_tradecraft(),
        egress="enclave",
    )
    by_key = {a.key: a for a in verdict.axes}
    assert {"read_only", "citations", "tradecraft", "egress"} <= set(by_key)
    assert by_key["read_only"].tier == HARD
    assert by_key["read_only"].pillar == "security"
    assert by_key["citations"].tier == HARD
    assert by_key["tradecraft"].tier == ADVISORY
    assert by_key["egress"].pillar == "data-integrity"


def test_to_payload_carries_status_ok_and_axes_for_persistence() -> None:
    verdict = build_verdict(
        governance=GovernanceReport(ok=True),
        citations=_clean_citations(),
        coverage=_full_coverage(),
        tradecraft=TradecraftReport(
            standard_terms=[], nonstandard_terms=["possibly"], has_confidence_statement=False
        ),
        egress="enclave",
    )
    payload = verdict.to_payload()
    assert payload["status"] == ADVISORY
    assert payload["ok"] is True
    keys = {a["key"] for a in payload["axes"]}
    assert {"read_only", "citations", "tradecraft", "egress"} == keys
    read_only = next(a for a in payload["axes"] if a["key"] == "read_only")
    assert read_only["tier"] == HARD
    assert read_only["status"] == PASS
    assert "label" in read_only and "pillar" in read_only and "detail" in read_only


def test_coverage_fraction_surfaces_in_the_citations_axis_detail() -> None:
    verdict = build_verdict(
        governance=GovernanceReport(ok=True),
        citations=_clean_citations(),
        coverage=CoverageStats(covered=3, total=4, fraction=0.75),
        tradecraft=_clean_tradecraft(),
        egress="enclave",
    )
    citations_axis = next(a for a in verdict.axes if a.key == "citations")
    assert "75%" in citations_axis.detail


def test_unrecorded_coverage_does_not_claim_zero_citable_claims() -> None:
    # coverage=None means "not recorded for this run", NOT "no citable claims" — an
    # uncited claim can coexist with it, so the detail must not misreport emptiness.
    verdict = build_verdict(
        governance=GovernanceReport(ok=True),
        citations=CitationReport(
            ok=False, cited=[], dangling=[], unused=[], uncited=["a claim"], unsupported=[]
        ),
        coverage=None,
        tradecraft=_clean_tradecraft(),
        egress="enclave",
    )
    citations_axis = next(a for a in verdict.axes if a.key == "citations")
    assert "no citable claims" not in citations_axis.detail
    assert "1 uncited" in citations_axis.detail
