"""Unit tests for ariadne.runs — run identity, paths, manifest, latest (ADR-0021)."""

from __future__ import annotations

from ariadne.runs import slug


def test_slug_lowercases_and_replaces_nonalnum():
    assert slug("Halberd") == "halberd"
    assert slug("vince.kaminski@enron.com") == "vince-kaminski-enron-com"


def test_slug_empty_falls_back_to_entity():
    assert slug("!!!") == "entity"
