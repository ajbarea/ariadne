from __future__ import annotations

from ariadne.evaluation.utilization import context_utilization


def test_utilization_is_cited_over_distinct_retrieved() -> None:
    note = "Halberd leads [cite:g1]. Tie to Talon [cite:g2]."
    # g3 retrieved but uncited — a legitimate exploratory / negative-confirmation call
    ledger = [{"id": "g1"}, {"id": "g2"}, {"id": "g3"}]
    assert context_utilization(note, ledger) == 2 / 3


def test_utilization_is_none_when_nothing_was_retrieved() -> None:
    # No denominator -> None (not a 0.0 that would read as "all noise")
    assert context_utilization("a claim [cite:g1]", []) is None


def test_dangling_citation_is_excluded_from_the_numerator() -> None:
    # g9 is cited but never retrieved — a citation error, not utilization.
    note = "Claim [cite:g1]. Bogus [cite:g9]."
    ledger = [{"id": "g1"}, {"id": "g2"}]
    assert context_utilization(note, ledger) == 1 / 2  # of {g1,g2} retrieved, only g1 cited


def test_distinct_retrieved_dedupes_repeated_calls() -> None:
    note = "[cite:g1]"
    ledger = [{"id": "g1"}, {"id": "g1"}, {"id": "g2"}]  # g1 queried twice
    assert context_utilization(note, ledger) == 1 / 2  # distinct retrieved {g1,g2}, cited {g1}
