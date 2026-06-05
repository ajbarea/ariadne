from __future__ import annotations

from ariadne.provenance.citations import (
    CitationReport,
    extract_citations,
    find_uncited_claims,
    validate_citations,
)
from ariadne.provenance.ledger import ProvenanceLedger


def _ledger_with(n: int) -> ProvenanceLedger:
    led = ProvenanceLedger()
    for i in range(n):
        led.record("mcp__neo4j__read_neo4j_cypher", {"query": f"Q{i + 1}"}, "r")
    return led


def test_extract_citations_finds_unique_ids_in_order() -> None:
    note = "Alpha reports to Bravo [cite:g1]. Bravo leads Unit-7 [cite:g2]. Recap [cite:g1]."
    assert extract_citations(note) == ["g1", "g2"]


def test_validate_passes_when_all_citations_resolve() -> None:
    led = ProvenanceLedger()
    led.record("mcp__neo4j__read_neo4j_cypher", {"query": "Q1"}, "r")
    led.record("mcp__neo4j__read_neo4j_cypher", {"query": "Q2"}, "r")
    report = validate_citations("Fact A [cite:g1]. Fact B [cite:g2].", led)
    assert isinstance(report, CitationReport)
    assert report.ok is True
    assert report.dangling == []
    assert report.unused == []


def test_validate_flags_dangling_citation() -> None:
    led = ProvenanceLedger()
    led.record("mcp__neo4j__read_neo4j_cypher", {"query": "Q1"}, "r")
    report = validate_citations("Real [cite:g1]. Fake [cite:g9].", led)
    assert report.ok is False
    assert report.dangling == ["g9"]


def test_validate_reports_unused_evidence() -> None:
    led = ProvenanceLedger()
    led.record("mcp__neo4j__read_neo4j_cypher", {"query": "Q1"}, "r")
    led.record("mcp__neo4j__read_neo4j_cypher", {"query": "Q2"}, "r")
    report = validate_citations("Only one fact [cite:g1].", led)
    assert report.ok is True  # unused is informational, not a failure
    assert report.unused == ["g2"]


# ── Coverage / citation-recall: the uncited-claim hole (ALCE citation recall) ──


def test_zero_citation_prose_note_fails_coverage() -> None:
    # The core governance hole: a note that asserts facts but cites NOTHING
    # used to pass. It must now fail.
    note = "## Summary\nHalberd leads the Signals-Cell unit and reports to HQ.\n"
    report = validate_citations(note, _ledger_with(1))
    assert report.ok is False
    assert report.uncited  # the uncited sentence is reported


def test_fully_cited_note_passes_coverage() -> None:
    note = "## Summary\nHalberd leads the Signals-Cell unit [cite:g1].\n"
    report = validate_citations(note, _ledger_with(1))
    assert report.ok is True
    assert report.uncited == []


def test_gaps_and_caveats_section_is_exempt_from_citation() -> None:
    # The note template declares caveats "(Citations optional here.)".
    note = (
        "## Summary\nHalberd leads Signals-Cell [cite:g1].\n\n"
        "## Gaps & caveats\nThe graph shows no financial or temporal links.\n"
    )
    report = validate_citations(note, _ledger_with(1))
    assert report.uncited == []
    assert report.ok is True


def test_provenance_section_is_exempt_from_citation() -> None:
    # The Provenance section echoes raw ledger queries; it is not claims.
    note = (
        "## Summary\nHalberd leads Signals-Cell [cite:g1].\n\n"
        "## Provenance\n- g1: MATCH (p:Person {name:'Halberd'}) RETURN p\n"
    )
    report = validate_citations(note, _ledger_with(1))
    assert report.uncited == []
    assert report.ok is True


def test_headers_and_blank_lines_are_not_claims() -> None:
    note = "# Analytic note: Halberd\n\n## Summary\n\nHalberd leads Signals-Cell [cite:g1].\n"
    report = validate_citations(note, _ledger_with(1))
    assert report.uncited == []
    assert report.ok is True


def test_uncited_sentence_in_summary_paragraph_is_flagged() -> None:
    note = (
        "## Summary\n"
        "Halberd leads the Signals-Cell unit [cite:g1]. "
        "He secretly controls the entire Directorate.\n"
    )
    report = validate_citations(note, _ledger_with(1))
    assert report.ok is False
    assert any("secretly controls" in c for c in report.uncited)


def test_find_uncited_claims_returns_the_uncited_sentence() -> None:
    uncited = find_uncited_claims("## Summary\nAlpha leads Bravo.\n")
    assert len(uncited) == 1
    assert "Alpha leads Bravo" in uncited[0]


def test_multi_sentence_bullet_with_trailing_citation_passes() -> None:
    # Real notes cite a multi-sentence bullet ONCE, at the end; that trailing
    # citation covers the whole segment (mirrors the shipped Halberd note's
    # bridge bullet). Must not be a false positive.
    note = (
        "## Relationships\n"
        "- Bridge: A connects to B via C. This shared link is decisive "
        "[cite:g1][cite:g2].\n"
    )
    report = validate_citations(note, _ledger_with(2))
    assert report.uncited == []
    assert report.ok is True


def test_claim_trailing_after_last_citation_in_segment_is_flagged() -> None:
    # A claim tacked on AFTER the segment's last citation is uncited.
    note = "## Relationships\n- A connects to B [cite:g1]. And A also secretly funds D.\n"
    report = validate_citations(note, _ledger_with(1))
    assert report.ok is False
    assert any("secretly funds D" in c for c in report.uncited)


def test_trailing_judgment_in_a_cited_segment_is_not_flagged() -> None:
    # Real example from a live Enron workup: a judgment trailing cited evidence.
    note = (
        "## Relationships\n"
        "- Of 38 external recipients, the leading domains are personal/webmail "
        "[cite:g10]. The webmail-heavy tail is consistent with the personal "
        "real-estate correspondence rather than counterparty trading flow.\n"
    )
    assert find_uncited_claims(note) == []


def test_trailing_therefore_judgment_in_a_cited_segment_is_not_flagged() -> None:
    # Live Halberd workup false positive: a "therefore" deduction trailing the
    # cited fact it rests on, within the same bullet, must not fail recall.
    note = (
        "## Organizational position\n"
        "- No REPORTS_TO edge originates from Halberd at the Person level "
        "[cite:g5][cite:g6]. Halberd's command linkage is therefore mediated "
        "entirely by the Signals-Cell unit node.\n"
    )
    assert find_uncited_claims(note) == []


def test_trailing_inferred_judgment_in_a_cited_segment_is_not_flagged() -> None:
    # Live Halberd workup false positive: a self-labeled "inferred" judgment
    # trailing its cited basis in the same bullet.
    note = (
        "## Relationships\n"
        "- Compound-Alpha is co-located with both cells [cite:g11]. Because the "
        "CO_LOCATED edges are unit-to-site, this is an inferred physical "
        "adjacency, not an asserted one.\n"
    )
    assert find_uncited_claims(note) == []


def test_standalone_judgment_without_any_citation_is_still_flagged() -> None:
    # A judgment in a segment with NO citation has no evidence to depend on.
    note = "## Summary\n- An analyst would miss that Rangel is the single conduit.\n"
    assert find_uncited_claims(note)  # non-empty: ungrounded judgment is flagged


def test_trailing_factual_claim_in_a_cited_segment_is_still_flagged() -> None:
    # A new FACT after a cite is not a judgment; it must carry its own cite.
    note = (
        "## Summary\n"
        "- Allen leads the West desk [cite:g1]. He also secretly owns a competitor firm.\n"
    )
    flagged = find_uncited_claims(note)
    assert any("secretly owns" in c for c in flagged)


def test_markdown_table_rows_are_not_treated_as_claims() -> None:
    note = (
        "## Graph footprint\n"
        "Her ties are summarized below [cite:g1]:\n"
        "| Direction | Counterparty | Msgs |\n"
        "| --- | --- | --- |\n"
        "| Ina -> other | information.management | 1 [cite:g5] |\n"
    )
    # The header and separator rows must NOT be flagged as uncited claims.
    flagged = find_uncited_claims(note)
    assert not any("Direction" in c or "---" in c for c in flagged)


def test_colon_terminated_lead_in_is_not_a_claim() -> None:
    note = "## Findings\n- The corpus shows the following:\n- Allen leads the desk [cite:g1].\n"
    flagged = find_uncited_claims(note)
    assert not any("following" in c for c in flagged)


def test_meta_analytic_caveat_is_exempt_from_uncited() -> None:
    from ariadne.provenance.citations import find_uncited_claims

    note = "## Findings\nH2 cannot be ruled out without a second modality."
    assert find_uncited_claims(note) == []  # evidential-limit statement, not a claim


def test_uncited_fact_in_findings_still_flagged() -> None:
    from ariadne.provenance.citations import find_uncited_claims

    note = "## Findings\nHalberd operates out of Compound-Alpha."
    assert find_uncited_claims(note) == ["Halberd operates out of Compound-Alpha."]
