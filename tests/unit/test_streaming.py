"""Tests for the bounded streaming helper shared by the HF-streaming adapters.

The key contract is that the underlying iterator is **closed** after the bound is
reached — abandoning a streaming dataset's iterator mid-shard leaves its prefetch
thread / open connection alive and hangs process teardown (observed on the
worldspeech audio stream).
"""

from __future__ import annotations

import time

import pytest

from ariadne.datasets.streaming import bounded_stream, stall_guarded


def test_yields_up_to_the_limit() -> None:
    assert list(bounded_stream(iter(range(100)), 3)) == [0, 1, 2]


def test_yields_all_when_source_is_shorter_than_the_limit() -> None:
    assert list(bounded_stream(iter([1, 2]), 10)) == [1, 2]


def test_predicate_filters_before_counting() -> None:
    rows = bounded_stream(iter(range(20)), 3, predicate=lambda n: n % 2 == 0)
    assert list(rows) == [0, 2, 4]  # 3 even rows, odds skipped (not counted)


def test_closes_the_underlying_iterator_after_the_bound() -> None:
    closed = {"v": False}

    def gen():
        try:
            i = 0
            while True:
                yield i
                i += 1
        finally:
            closed["v"] = True

    rows = list(bounded_stream(gen(), 3))
    assert rows == [0, 1, 2]
    assert closed["v"] is True  # explicitly closed, not left dangling for GC


def test_stall_guarded_passes_rows_through_when_progressing() -> None:
    # Takes a factory (called inside the daemon thread), not a ready iterable.
    assert list(stall_guarded(lambda: iter([1, 2, 3]), stall_timeout=5.0)) == [1, 2, 3]


def test_stall_guarded_raises_when_no_row_arrives_within_the_timeout() -> None:
    # A source that blocks longer than the stall timeout = a stalled stream.
    def stalling():
        yield 1
        time.sleep(1.0)  # > stall_timeout below
        yield 2

    rows = stall_guarded(stalling, stall_timeout=0.2)
    assert next(rows) == 1
    with pytest.raises(TimeoutError):
        next(rows)


def test_stall_guarded_guards_stream_creation_too() -> None:
    # The factory itself can block (e.g. load_dataset resolving over the network).
    # That must run inside the guarded thread, not the caller — else the guard is moot.
    def slow_to_create():
        time.sleep(1.0)  # > stall_timeout: simulates a stalled load_dataset()
        return iter([1, 2])

    rows = stall_guarded(slow_to_create, stall_timeout=0.2)
    with pytest.raises(TimeoutError):
        next(rows)


def test_stall_guarded_propagates_the_sources_own_error() -> None:
    def boom():
        yield 1
        raise ValueError("upstream failure")

    rows = stall_guarded(boom, stall_timeout=5.0)
    assert next(rows) == 1
    with pytest.raises(ValueError, match="upstream failure"):
        next(rows)
