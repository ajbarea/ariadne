"""Bounded consumption of a (possibly streaming) HF dataset iterator.

``bounded_stream`` yields up to ``limit`` rows, then **closes the underlying
iterator**. The close is the point: abandoning a streaming ``IterableDataset``
iterator mid-shard (the ``for row in stream: ...; break`` pattern) leaves its
open connection / prefetch thread alive, which hangs process teardown — the
worldspeech audio stream sat for 30+ minutes at 0% CPU on exit before this.
Closing raises ``GeneratorExit`` into the iterator so HF releases those
resources synchronously.
"""

from __future__ import annotations

import os
import queue
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator
    from typing import Any

# A streaming row gap longer than this means the connection stalled (the HF audio
# stream's CLOSE_WAIT hang), not slow-but-progressing. Generous so a legitimately
# slow shard fetch is not aborted. research(2026-06): HF streaming has no built-in
# read timeout on the shard-read path; a dead connection blocks forever (datasets
# #7467 / #3049), so the consumer must bound it. Tunable via $ARIADNE_STREAM_STALL_S.
DEFAULT_STALL_TIMEOUT_S = 180.0


def bounded_stream(
    stream: Iterable[Any],
    limit: int,
    *,
    predicate: Callable[[Any], bool] | None = None,
) -> Iterator[Any]:
    """Yield up to ``limit`` rows from ``stream`` (optionally filtered), then close it.

    ``predicate`` rows that fail the filter are skipped and do not count toward
    ``limit``. The underlying iterator is closed in a ``finally`` so a streaming
    source's resources are released even if the consumer stops early.
    """
    it = iter(stream)
    try:
        taken = 0
        for row in it:
            if predicate is not None and not predicate(row):
                continue
            yield row
            taken += 1
            if taken >= limit:
                break
    finally:
        close = getattr(it, "close", None)
        if callable(close):
            close()


def stall_guarded(
    make_stream: Callable[[], Iterable[Any]], *, stall_timeout: float
) -> Iterator[Any]:
    """Yield from a stream but raise ``TimeoutError`` if a row takes longer than
    ``stall_timeout`` seconds to arrive — a stalled connection, not a slow one.

    Takes a **factory**, not a ready iterable: ``make_stream()`` is called on the
    daemon thread so the *creation* call (``load_dataset(streaming=True)``, itself a
    blocking network resolve) is guarded too — calling it in the caller's thread to
    build an argument would hang outside the guard, which was the whole bug. The
    daemon thread is the other half: even if a socket read is wedged (``CLOSE_WAIT``),
    a daemon never blocks interpreter exit. The source's own errors are re-raised.
    """
    q: queue.Queue[tuple[Any, BaseException | None]] = queue.Queue(maxsize=1)
    done = object()

    def pump() -> None:
        try:
            for item in make_stream():
                q.put((item, None))
        except BaseException as exc:  # propagate upstream failure to the consumer
            q.put((done, exc))
        else:
            q.put((done, None))

    threading.Thread(target=pump, name="ariadne-stream", daemon=True).start()
    while True:
        try:
            item, exc = q.get(timeout=stall_timeout)
        except queue.Empty:
            raise TimeoutError(
                f"stream stalled: no row within {stall_timeout:.0f}s (likely a dead "
                "connection) — aborting the index"
            ) from None
        if item is done:
            if exc is not None:
                raise exc
            return
        yield item


def stall_timeout_s() -> float:
    """Per-row stall timeout for the live streams, overridable via $ARIADNE_STREAM_STALL_S."""
    raw = os.environ.get("ARIADNE_STREAM_STALL_S")
    try:
        return float(raw) if raw else DEFAULT_STALL_TIMEOUT_S
    except ValueError:
        return DEFAULT_STALL_TIMEOUT_S
