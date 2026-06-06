"""Command-line entrypoint for Ariadne."""

from __future__ import annotations

import os
import sys

from ariadne.cli import main as _run


def main(argv: list[str] | None = None) -> int:
    """Run the CLI, then exit.

    research(2026-06): once ``torch`` is imported — the ``datasets`` audio schema,
    sentence-transformers, and HHEM all pull it in — its core threading segfaults at
    Python interpreter finalization (``PyGILState_Release``, exit 134) on some envs
    (e.g. 3.12 + WSL2). The command's work is already committed by the time we return, so
    when torch is loaded we flush stdout/stderr and ``os._exit`` immediately, skipping the
    buggy finalization. This is the recognized fix for the torch shutdown-crash class; it
    stays inert when torch was never imported (the common, non-ML path).
    """
    rc = _run(argv)
    if "torch" in sys.modules:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
