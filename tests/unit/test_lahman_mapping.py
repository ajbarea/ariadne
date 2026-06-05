from __future__ import annotations

from ariadne.datasets.canonical import Entity, Relationship
from ariadne.datasets.lahman import map_lahman

_PEOPLE = [
    {
        "playerID": "ruthba01",
        "nameFirst": "Babe",
        "nameLast": "Ruth",
        "nameGiven": "George Herman",
        "bats": "L",
        "throws": "L",
        "birthYear": "1895",
        "birthCountry": "USA",
    },
    {
        "playerID": "gehrlo01",
        "nameFirst": "Lou",
        "nameLast": "Gehrig",
        "nameGiven": "Henry Louis",
        "bats": "L",
        "throws": "L",
        "birthYear": "1903",
        "birthCountry": "USA",
    },
]
_BATTING = [
    {"playerID": "ruthba01", "yearID": "1927", "stint": "1", "teamID": "NYA", "lgID": "AL"},
    {"playerID": "gehrlo01", "yearID": "1927", "stint": "1", "teamID": "NYA", "lgID": "AL"},
]


def test_people_become_player_entities_keyed_by_playerid() -> None:
    recs = list(map_lahman(_PEOPLE, _BATTING))
    ruth = next(r for r in recs if isinstance(r, Entity) and r.id == "person:ruthba01")
    assert ruth.type == "person"
    assert ruth.name == "Babe Ruth"
    assert "ruthba01" in ruth.aliases  # the canonical key is a resolvable alias
    assert ruth.attributes["birthYear"] == "1895"


def test_teams_become_deduped_entities() -> None:
    recs = list(map_lahman(_PEOPLE, _BATTING))
    teams = [r for r in recs if isinstance(r, Entity) and r.type == "team"]
    assert [t.id for t in teams] == ["team:NYA"]  # both players' NYA collapses to one


def test_played_for_edges_link_player_to_team_with_year() -> None:
    recs = list(map_lahman(_PEOPLE, _BATTING))
    edges = [r for r in recs if isinstance(r, Relationship) and r.type == "PLAYED_FOR"]
    ruth_edge = next(e for e in edges if e.src == "person:ruthba01")
    assert ruth_edge.dst == "team:NYA"
    assert ruth_edge.attributes["yearID"] == "1927"


def test_shared_team_year_makes_players_reachable_as_teammates() -> None:
    # Both 1927 Yankees -> two PLAYED_FOR edges into team:NYA: the multi-hop
    # teammate path (Ruth -> NYA -> Gehrig) the relational/ER demo needs.
    recs = list(map_lahman(_PEOPLE, _BATTING))
    into_nya = {e.src for e in recs if isinstance(e, Relationship) and e.dst == "team:NYA"}
    assert into_nya == {"person:ruthba01", "person:gehrlo01"}
