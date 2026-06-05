from __future__ import annotations

import os
import pathlib
from typing import LiteralString, cast

import pytest

pytest.importorskip("testcontainers")

from neo4j import GraphDatabase
from testcontainers.neo4j import Neo4jContainer

SEED = pathlib.Path("infra/neo4j/seed.cypher")

# Colima uses a non-default socket; wire it up when the standard socket is absent
# and the Colima socket exists.  Ryuk cannot mount the socket path inside Colima
# containers, so disable it unconditionally here.
_COLIMA_SOCK = pathlib.Path.home() / ".colima" / "default" / "docker.sock"
_DEFAULT_SOCK = pathlib.Path("/var/run/docker.sock")

if not _DEFAULT_SOCK.exists() and _COLIMA_SOCK.exists():
    os.environ.setdefault("DOCKER_HOST", f"unix://{_COLIMA_SOCK}")

os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")


def _docker_reachable() -> bool:
    # research(2026-06): testcontainers-python's recommended availability guard is
    # docker.from_env().ping(). Run it AFTER the DOCKER_HOST wiring above so the
    # Colima socket is honored. Lets integration tests SKIP with a clear reason
    # when no daemon is up, instead of erroring at container creation.
    try:
        import docker

        docker.from_env().ping()
    except Exception:
        return False
    return True


_DOCKER_AVAILABLE = _docker_reachable()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Skip Docker-backed integration tests when no daemon is reachable. Scoped to
    the ``integration`` marker, minus ``network`` tests (HF streaming etc. need a
    network, not Docker), so unit and network-only tests are untouched; the skip is
    reported in pytest output (visible, never silent)."""
    if _DOCKER_AVAILABLE:
        return
    skip = pytest.mark.skip(
        reason="Docker daemon not reachable; start Colima/Docker to run integration tests."
    )
    for item in items:
        if item.get_closest_marker("integration") and not item.get_closest_marker("network"):
            item.add_marker(skip)


def _statements(cypher: str) -> list[str]:
    lines = [ln for ln in cypher.splitlines() if not ln.strip().startswith("//")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


@pytest.fixture(scope="session")
def neo4j_conn():
    with Neo4jContainer("neo4j:5.26-community") as neo:
        uri = neo.get_connection_url()
        username = neo.username
        password = neo.password
        driver = GraphDatabase.driver(uri, auth=(username, password))
        with driver.session() as session:
            for stmt in _statements(SEED.read_text()):
                session.run(cast("LiteralString", stmt))
        driver.close()
        yield {"uri": uri, "username": username, "password": password}
