"""Smoke tests — prove the package imports and the CLI runs.

These keep the toolchain honest (lint/test wired correctly) before any real
architecture exists. Replace/extend as the harness takes shape.
"""

from __future__ import annotations

import ariadne
from ariadne.__main__ import main


def test_version_is_set() -> None:
    assert ariadne.__version__
    assert isinstance(ariadne.__version__, str)


def test_cli_default_runs() -> None:
    assert main([]) == 0


def test_cli_version_flag() -> None:
    assert main(["--version"]) == 0
