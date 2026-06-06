"""Unit tests for ariadne.runs — run identity, paths, manifest, latest (ADR-0021)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ariadne.runs import run_dir, run_id, slug


def test_slug_lowercases_and_replaces_nonalnum():
    assert slug("Halberd") == "halberd"
    assert slug("vince.kaminski@enron.com") == "vince-kaminski-enron-com"


def test_slug_empty_falls_back_to_entity():
    assert slug("!!!") == "entity"


def test_run_id_uses_trace_prefix_when_present():
    now = datetime(2026, 6, 5, 18, 23, 1, tzinfo=UTC)
    rid = run_id(now, trace_hex="4bf92f3577b34da6a3ce929d0e0e4736")
    assert rid == "2026-06-05T18-23-01Z-4bf92f35"


def test_run_id_random_suffix_when_no_trace():
    now = datetime(2026, 6, 5, 18, 23, 1, tzinfo=UTC)
    a = run_id(now, trace_hex="")
    b = run_id(now, trace_hex="")
    assert a.startswith("2026-06-05T18-23-01Z-")
    assert len(a.rsplit("-", 1)[1]) == 8
    assert a != b  # random suffix disambiguates same-second runs


def test_run_dir_composes_dataset_slug_runid():
    now = datetime(2026, 6, 5, 18, 23, 1, tzinfo=UTC)
    d = run_dir("runs", "synthetic", "Halberd", now=now, trace_hex="4bf92f35aaaaaaaa")
    assert d == Path("runs/synthetic/halberd/2026-06-05T18-23-01Z-4bf92f35")


def test_run_dir_two_calls_never_collide():
    now = datetime(2026, 6, 5, 18, 23, 1, tzinfo=UTC)
    a = run_dir("runs", "synthetic", "Halberd", now=now)  # no trace -> random suffix
    b = run_dir("runs", "synthetic", "Halberd", now=now)
    assert a != b  # the no-overwrite property
