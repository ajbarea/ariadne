"""Live Lahman load from Hugging Face (CSV download; needs the `data` extra + network)."""

from __future__ import annotations

import pytest

pytest.importorskip("huggingface_hub")

from ariadne.datasets.canonical import Entity, Relationship
from ariadne.datasets.lahman import LahmanAdapter

pytestmark = [pytest.mark.integration, pytest.mark.network]


def test_lahman_download_maps_players_teams_and_played_for() -> None:
    recs = list(LahmanAdapter(limit=300).load())
    assert any(isinstance(r, Entity) and r.type == "person" for r in recs)
    assert any(isinstance(r, Entity) and r.type == "team" for r in recs)
    edges = [r for r in recs if isinstance(r, Relationship) and r.type == "PLAYED_FOR"]
    assert edges and all(e.dst.startswith("team:") for e in edges)
