from __future__ import annotations

from typing import Literal, cast

import pytest

from ariadne.datasets.base import DATASETS, DatasetAdapter, get_adapter, register
from ariadne.datasets.canonical import Entity


class _FakeAdapter:
    name: str = "fake"
    entity_type: str = "person"
    access: Literal["public"] = "public"

    def load(self):
        yield Entity(id="person:X", type="person", name="X")

    def eval_fixtures(self):
        return []


def test_register_then_get_round_trips() -> None:
    adapter = cast("DatasetAdapter", _FakeAdapter())
    register(adapter)
    assert "fake" in DATASETS
    assert get_adapter("fake").entity_type == "person"


def test_unknown_dataset_raises_keyerror_listing_known() -> None:
    with pytest.raises(KeyError):
        get_adapter("nope")
