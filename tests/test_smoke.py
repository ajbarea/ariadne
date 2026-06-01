"""Smoke tests — prove the package imports and the CLI wiring is present."""

from __future__ import annotations

import pytest

import ariadne
from ariadne.__main__ import main


def test_version_is_set() -> None:
    assert ariadne.__version__
    assert isinstance(ariadne.__version__, str)


def test_cli_requires_subcommand() -> None:
    with pytest.raises(SystemExit):
        main([])
