from __future__ import annotations

import pytest

from ariadne.cli import parse_args


def test_index_defaults_to_synthetic() -> None:
    args = parse_args(["index"])
    assert args.command == "index" and args.dataset == "synthetic"


def test_index_rejects_unknown_dataset() -> None:
    with pytest.raises(SystemExit):
        parse_args(["index", "--dataset", "nope"])
