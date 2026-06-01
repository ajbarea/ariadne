"""Command-line entrypoint for Ariadne.

Placeholder until the harness wiring lands (see ROADMAP.md, Phase 1). For now it
just confirms the install and prints the version so ``make dev`` /
``uv run ariadne`` exercises the package end to end.
"""

from __future__ import annotations

import sys

from ariadne import __version__


def main(argv: list[str] | None = None) -> int:
    """Entrypoint. Returns a process exit code."""
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] in {"-v", "--version"}:
        print(f"ariadne {__version__}")
        return 0
    print(f"ariadne {__version__} — sensemaking harness (scaffold)")
    print("Architecture pending June-2026 research; see ROADMAP.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
