"""Pre-flight store reachability — fast-fail with an actionable message before the agent loop.

The #1 first-run live failure is "I didn't start the database." Catch it before spending an
API call: a conservative TCP probe that blocks only on a definitive connection-refused (the
store isn't up), never on an ambiguous timeout/DNS failure.
"""

from __future__ import annotations

from ariadne.preflight import host_port, store_unreachable, workup_preflight

_NEO4J = "bolt://localhost:7687"
_PG = "postgresql://ariadne:ariadne@db.example:5432/intel"


def test_host_port_parses_bolt_and_postgres_with_defaults() -> None:
    assert host_port(_NEO4J) == ("localhost", 7687)
    assert host_port(_PG) == ("db.example", 5432)
    assert host_port("bolt://myhost") == ("myhost", 7687)  # default bolt port
    assert host_port("postgresql://u:p@h/db") == ("h", 5432)  # default pg port


def test_store_unreachable_reports_when_refused() -> None:
    msg = store_unreachable(
        _NEO4J, label="Neo4j", fix="Start it with docker compose.", refused=lambda h, p: True
    )
    assert msg is not None
    assert "Neo4j" in msg and "localhost:7687" in msg
    assert "Start it with docker compose." in msg  # the remediation is declared, not inferred


def test_store_reachable_returns_none() -> None:
    assert store_unreachable(_NEO4J, label="Neo4j", fix="x", refused=lambda h, p: False) is None


def test_preflight_always_checks_neo4j() -> None:
    refused = {("localhost", 7687)}  # neo4j down
    msg = workup_preflight(
        {}, with_sql=False, with_semantic=False, refused=lambda h, p: (h, p) in refused
    )
    assert msg is not None
    assert "graph" in msg.lower() or "neo4j" in msg.lower()
    assert "docker compose" in msg  # actionable


def test_preflight_checks_postgres_only_when_sql_or_semantic() -> None:
    # Only Postgres is down. Without --sql/--semantic, that's not consulted -> no block.
    refused_pg = lambda h, p: p == 5432  # noqa: E731
    assert workup_preflight({}, with_sql=False, with_semantic=False, refused=refused_pg) is None
    msg = workup_preflight({}, with_sql=True, with_semantic=False, refused=refused_pg)
    assert msg is not None
    assert "5432" in msg


def test_preflight_passes_when_all_reachable() -> None:
    assert (
        workup_preflight({}, with_sql=True, with_semantic=True, refused=lambda h, p: False) is None
    )
