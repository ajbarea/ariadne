"""Gated integration test for the real HHEM-backed entailment verifier.

Skipped unless the optional ``eval`` extra is installed (``uv sync --extra eval``);
downloads the HHEM-2.1-Open model on first run. Mirrors the key-gated live-agent
e2e pattern — the hermetic suite never touches the model.
"""

from __future__ import annotations

import pytest

pytest.importorskip("transformers")

from ariadne.provenance.citations import find_unsupported_claims, validate_citations
from ariadne.provenance.entailment import HHEMVerifier
from ariadne.provenance.ledger import ProvenanceLedger

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def hhem() -> HHEMVerifier:
    return HHEMVerifier()


def test_hhem_distinguishes_supported_from_contradicted(hhem: HHEMVerifier) -> None:
    evidence = "Halberd MEMBER_OF Signals-Cell (echelon 3)"
    assert hhem.entails("Halberd is a member of Signals-Cell", evidence) is True
    assert hhem.entails("Halberd commands the entire Directorate", evidence) is False


def test_unsupported_claim_caught_end_to_end(hhem: HHEMVerifier) -> None:
    led = ProvenanceLedger()
    led.record("mcp__neo4j__read_neo4j_cypher", {"query": "Q1"}, "Halberd MEMBER_OF Signals-Cell")
    note = "## Summary\nHalberd commands the entire Directorate [cite:g1].\n"
    report = validate_citations(note, led, verifier=hhem)
    assert report.ok is False
    assert report.unsupported
    assert find_unsupported_claims(note, led, hhem)
