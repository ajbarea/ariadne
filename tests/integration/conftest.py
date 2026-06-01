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
