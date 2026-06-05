"""Lahman Baseball Database (`NeuML/baseballdata`) as a RELATIONAL dataset adapter.

The structured / entity-resolution counterpart to the document (enron) and audio
(worldspeech) connectors: clean shared keys (``playerID`` / ``teamID`` /
``yearID``) exercise the relational store + tiered entity resolution (ADR-0016)
and multi-hop graph reasoning (player -> team -> teammate).

The HF copy is plain CSVs (People/Batting/Pitching/Fielding) with no parquet /
loading script, so this is a **cache-aware download** (``hf_hub_download``), not a
stream. ``map_lahman`` is a pure transform (fabricated rows in tests).
"""

from __future__ import annotations

import csv
import itertools
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from ariadne.datasets.base import register
from ariadne.datasets.canonical import Canonical, Entity, Relationship

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from ariadne.evaluation.needle import NeedleFixture

_PERSON_ATTRS = ("birthYear", "birthCountry", "bats", "throws")


def map_lahman(people: Iterable[dict], *stat_tables: Iterable[dict]) -> Iterator[Canonical]:
    """Map Lahman rows to canonical records.

    ``people`` rows become player Entities keyed by ``playerID`` (also kept as an
    alias so the canonical key resolves). Each stat-table row (batting / pitching /
    fielding) yields a ``team`` Entity (deduped) and a ``PLAYED_FOR`` edge
    ``person -> team`` carrying ``yearID``; a player + teammate share a team-year,
    giving the multi-hop path the relational/ER demo needs.
    """
    players: dict[str, Entity] = {}
    for row in people:
        pid = str(row.get("playerID") or "").strip()
        if not pid:
            continue
        name = f"{row.get('nameFirst', '')} {row.get('nameLast', '')}".strip()
        aliases = tuple(a for a in (pid, str(row.get("nameGiven") or "").strip()) if a)
        attrs = {k: str(row[k]) for k in _PERSON_ATTRS if row.get(k)}
        players.setdefault(
            f"person:{pid}",
            Entity(
                id=f"person:{pid}",
                type="person",
                name=name or pid,
                aliases=aliases,
                attributes=attrs,
            ),
        )

    teams: dict[str, Entity] = {}
    edges: dict[tuple[str, str, str], Relationship] = {}
    for row in itertools.chain.from_iterable(stat_tables):
        pid = str(row.get("playerID") or "").strip()
        tid = str(row.get("teamID") or "").strip()
        if not pid or not tid:
            continue
        team_key = f"team:{tid}"
        teams.setdefault(team_key, Entity(id=team_key, type="team", name=tid))
        year = str(row.get("yearID") or "")
        ekey = (pid, tid, year)
        edges.setdefault(
            ekey,
            Relationship(
                src=f"person:{pid}",
                dst=team_key,
                type="PLAYED_FOR",
                attributes={
                    "yearID": year,
                    "lgID": str(row.get("lgID") or ""),
                    "stint": str(row.get("stint") or ""),
                },
            ),
        )

    yield from players.values()
    yield from teams.values()
    yield from edges.values()


_REPO = "NeuML/baseballdata"
_PEOPLE_FILE = "People.csv"
_STAT_FILES = ("Batting.csv", "Pitching.csv", "Fielding.csv")
_DEFAULT_LIMIT = 2000


class LahmanAdapter:
    """Downloads the NeuML Lahman CSVs (cache-aware) and maps them to canonical.

    ``limit`` bounds rows read per table for fast demo/CI runs. CC-BY-SA-3.0.
    """

    name: str = "lahman"
    entity_type: str = "person"
    access: Literal["public", "restricted"] = "public"

    def __init__(self, limit: int = _DEFAULT_LIMIT) -> None:
        self.limit = limit

    def _rows(self, filename: str) -> list[dict]:
        # Lazy import so the static checker stays stable without the `data` extra.
        import importlib

        hf_hub_download = importlib.import_module("huggingface_hub").hf_hub_download
        path = hf_hub_download(repo_id=_REPO, repo_type="dataset", filename=filename)
        with Path(path).open(encoding="utf-8", newline="") as fh:
            return list(itertools.islice(csv.DictReader(fh), self.limit))

    def load(self) -> Iterator[Canonical]:
        people = self._rows(_PEOPLE_FILE)
        stats = [self._rows(f) for f in _STAT_FILES]
        return map_lahman(people, *stats)

    def eval_fixtures(self) -> list[NeedleFixture]:
        # Relational ingestion / ER proof; a planted needle needs known rows, so
        # none here (mirrors worldspeech).
        return []


register(LahmanAdapter())
