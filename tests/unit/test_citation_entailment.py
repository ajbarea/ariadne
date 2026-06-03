"""Stage 2 — entailment / precision: does the cited evidence support the claim?

Unit-tested against a fake verifier (dependency injection) so the suite stays
hermetic; the real HHEM-backed verifier is exercised by a gated integration test.
"""

from __future__ import annotations

from ariadne.provenance.citations import (
    find_unsupported_claims,
    validate_citations,
)
from ariadne.provenance.ledger import ProvenanceLedger


class _PresetVerifier:
    """Fake EntailmentVerifier: claims containing a key get that verdict.

    Records every (claim, evidence) pair so tests can assert the cited evidence
    was actually passed through.
    """

    def __init__(self, verdicts: dict[str, bool] | None = None, default: bool = True) -> None:
        self.verdicts = verdicts or {}
        self.default = default
        self.calls: list[tuple[str, str]] = []

    def entails(self, claim: str, evidence: str) -> bool:
        self.calls.append((claim, evidence))
        for key, verdict in self.verdicts.items():
            if key in claim:
                return verdict
        return self.default


def _ledger(*excerpts: str) -> ProvenanceLedger:
    led = ProvenanceLedger()
    for i, ex in enumerate(excerpts):
        led.record("mcp__neo4j__read_neo4j_cypher", {"query": f"Q{i + 1}"}, ex)
    return led


def test_unsupported_claim_is_flagged() -> None:
    led = _ledger("Bravo is a Unit node")
    note = "## Summary\nAlpha secretly funds Bravo [cite:g1].\n"
    verifier = _PresetVerifier({"secretly funds": False})
    report = validate_citations(note, led, verifier=verifier)
    assert report.ok is False
    assert any("secretly funds" in c for c in report.unsupported)


def test_supported_claim_passes() -> None:
    led = _ledger("Alpha MEMBER_OF Bravo")
    note = "## Summary\nAlpha is a member of Bravo [cite:g1].\n"
    report = validate_citations(note, led, verifier=_PresetVerifier(default=True))
    assert report.ok is True
    assert report.unsupported == []


def test_no_verifier_skips_entailment() -> None:
    # Backward compatible: without a verifier, Stage 2 does not run (no model needed).
    led = _ledger("anything")
    note = "## Summary\nAlpha funds Bravo [cite:g1].\n"
    report = validate_citations(note, led)
    assert report.unsupported == []
    assert report.ok is True


def test_entailment_is_checked_against_the_cited_ledger_excerpt() -> None:
    led = _ledger("first", "the decisive co-location evidence")
    note = "## Summary\nAlpha bridges to Bravo [cite:g2].\n"
    verifier = _PresetVerifier(default=True)
    validate_citations(note, led, verifier=verifier)
    # the claim was checked against g2's excerpt, not g1's
    assert verifier.calls
    _claim, evidence = verifier.calls[0]
    assert "decisive co-location evidence" in evidence
    assert "first" not in evidence


def test_uncited_claim_is_not_sent_to_the_verifier() -> None:
    # An uncited claim is a recall failure (Stage 1), not an entailment one.
    led = _ledger("evidence")
    note = "## Summary\nAlpha leads Bravo [cite:g1]. Bravo controls everything.\n"
    verifier = _PresetVerifier(default=True)
    report = validate_citations(note, led, verifier=verifier)
    assert all("controls everything" not in claim for claim, _ in verifier.calls)
    assert any("controls everything" in c for c in report.uncited)


def test_estimative_claims_are_exempt_from_the_entailment_gate() -> None:
    # An analytic judgment ("likely") is a calibrated inference, not a fact the
    # evidence directly entails — entailment is the wrong test for it, so even a
    # reject-everything verifier must not flag it. It is governed by the tradecraft
    # calibration lint instead. A neighbouring factual claim is still checked.
    led = _ledger("Halberd is a member of Signals-Cell", "Wren is a member of Logistics-Cell")
    note = (
        "## Summary\n"
        "Halberd is likely the signals lead [cite:g1].\n"
        "Halberd secretly funds Wren [cite:g2].\n"
    )
    verifier = _PresetVerifier(default=False)  # rejects every claim it is asked about
    report = validate_citations(note, led, verifier=verifier)
    assert all("likely the signals lead" not in claim for claim, _ in verifier.calls)
    assert all("likely the signals lead" not in c for c in report.unsupported)
    assert any("secretly funds" in c for c in report.unsupported)


def test_find_unsupported_claims_strips_cite_markers_from_claim() -> None:
    led = _ledger("evidence text")
    verifier = _PresetVerifier(default=True)
    find_unsupported_claims("## Summary\nAlpha leads Bravo [cite:g1].\n", led, verifier)
    claim, _evidence = verifier.calls[0]
    assert "[cite:g1]" not in claim
    assert "Alpha leads Bravo" in claim
