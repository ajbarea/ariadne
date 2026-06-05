"""ICD-203 tradecraft lint — estimative-language standardization."""

from __future__ import annotations

from ariadne.provenance.tradecraft import (
    TradecraftReport,
    is_estimative,
    lint_estimative_language,
)


def test_detects_standard_wep_term_with_band() -> None:
    report = lint_estimative_language("Halberd is likely the cell lead [cite:g1].")
    assert isinstance(report, TradecraftReport)
    assert ("likely", "55-80%") in report.standard_terms


def test_very_likely_is_not_double_counted_as_likely() -> None:
    report = lint_estimative_language("A co-location is very likely [cite:g1].")
    assert ("very likely", "80-95%") in report.standard_terms
    assert all(term != "likely" for term, _band in report.standard_terms)


def test_flags_nonstandard_hedge() -> None:
    report = lint_estimative_language("Halberd possibly commands the cell.")
    assert "possibly" in report.nonstandard_terms
    assert report.standard_terms == []


def test_detects_analytic_confidence_statement() -> None:
    report = lint_estimative_language("Assessed with moderate confidence [cite:g1].")
    assert report.has_confidence_statement is True


def test_clean_note_has_no_findings() -> None:
    report = lint_estimative_language("Halberd is a member of Signals-Cell [cite:g1].")
    assert report.standard_terms == []
    assert report.nonstandard_terms == []
    assert report.has_confidence_statement is False


def test_matching_is_case_insensitive() -> None:
    report = lint_estimative_language("Perhaps the link is Unlikely.")
    assert "perhaps" in report.nonstandard_terms
    assert ("unlikely", "20-45%") in report.standard_terms


def test_is_estimative_detects_a_standard_wep_term() -> None:
    assert is_estimative("Halberd is likely the signals lead") is True


def test_is_estimative_detects_a_nonstandard_hedge() -> None:
    assert is_estimative("Halberd is possibly the signals lead") is True


def test_is_estimative_detects_an_analytic_confidence_statement() -> None:
    assert is_estimative("Assessed with moderate confidence.") is True


def test_is_estimative_is_false_for_a_plain_factual_claim() -> None:
    assert is_estimative("Halberd is a member of the Signals-Cell") is False


def test_is_analytic_judgment_detects_inference_and_estimative() -> None:
    from ariadne.provenance.tradecraft import is_analytic_judgment

    assert is_analytic_judgment("This is consistent with a gatekeeper role")
    assert is_analytic_judgment("Halberd is likely the lead")  # estimative
    assert is_analytic_judgment("an analyst would miss the bridge")
    assert is_analytic_judgment("Halberd is a member of Signals-Cell") is False


def test_is_analytic_judgment_detects_reveals_and_understates() -> None:
    from ariadne.provenance.tradecraft import is_analytic_judgment

    assert is_analytic_judgment("the email-body modality reveals a gatekeeper role")
    assert is_analytic_judgment("the graph-only view understates her access")


def test_is_analytic_judgment_detects_illative_connectives() -> None:
    # Canonical conclusion indicators (therefore/thus/hence/...) and the self-label
    # "inferred" mark a deduction, not a sourced fact — both seen trailing cited
    # evidence in a live Halberd workup.
    from ariadne.provenance.tradecraft import is_analytic_judgment

    assert is_analytic_judgment("Halberd's command linkage is therefore mediated by the unit node")
    assert is_analytic_judgment("this is an inferred physical adjacency, not an asserted one")


def test_is_analytic_caveat_detects_insufficiency() -> None:
    from ariadne.provenance.tradecraft import is_analytic_caveat

    assert is_analytic_caveat("H2 cannot be ruled out without a second modality.")
    assert is_analytic_caveat("This requires corroboration from imagery.")


def test_is_analytic_caveat_false_for_a_plain_claim() -> None:
    from ariadne.provenance.tradecraft import is_analytic_caveat

    assert not is_analytic_caveat("Halberd is co-located with Talon at Compound-Alpha.")
