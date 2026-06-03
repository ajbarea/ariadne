from __future__ import annotations

import pytest

from ariadne.cli import parse_args


def test_workup_defaults_to_synthetic_dataset() -> None:
    args = parse_args(["workup", "Halberd"])
    assert args.dataset == "synthetic"


def test_workup_accepts_a_known_dataset() -> None:
    args = parse_args(["workup", "Halberd", "--dataset", "synthetic"])
    assert args.dataset == "synthetic"


def test_unknown_dataset_is_rejected_by_argparse() -> None:
    with pytest.raises(SystemExit):
        parse_args(["workup", "Halberd", "--dataset", "nope"])
