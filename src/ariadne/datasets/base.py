"""Dataset adapter contract + registry.

A dataset is added by implementing ``DatasetAdapter`` and registering it. The
agent, connectors, skill, and eval harness never change — only an adapter does.
Mirrors the ``FIXTURES`` registry idiom in ``evaluation/needle.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Iterable

    from ariadne.datasets.canonical import Canonical
    from ariadne.evaluation.needle import NeedleFixture


@runtime_checkable
class DatasetAdapter(Protocol):
    name: str
    entity_type: str
    access: Literal["public", "restricted"]

    def load(self) -> Iterable[Canonical]: ...

    def eval_fixtures(self) -> list[NeedleFixture]: ...


DATASETS: dict[str, DatasetAdapter] = {}


def register(adapter: DatasetAdapter) -> None:
    DATASETS[adapter.name] = adapter


def get_adapter(name: str) -> DatasetAdapter:
    try:
        return DATASETS[name]
    except KeyError as exc:
        raise KeyError(f"unknown dataset {name!r}; known: {sorted(DATASETS)}") from exc
