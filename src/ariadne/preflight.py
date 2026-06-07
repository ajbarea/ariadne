"""Pre-flight store reachability for `ariadne workup` (actionable, fast-fail, no spend).

The most common first-run live failure is "I didn't start the database." Before launching
the (paid) agent loop, probe the stores the run will use and, if one is definitively down,
print what is wrong and how to fix it. Conservative by design: it blocks only on a TCP
**connection-refused** (the store isn't listening), never on an ambiguous timeout/DNS error,
so a slow or remote store is never falsely blocked.

# research(2026-06): actionable, dual-consumer CLI errors -- state the remediation, don't make
# the human or the driving agent infer it; fast-fail before spend. ADR-0009 (MCP/CLI surface).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from collections.abc import Callable

_NEO4J_DEFAULT = "bolt://localhost:7687"
_PG_DEFAULT = "postgresql://ariadne:ariadne@localhost:5432/intel"


def host_port(uri: str) -> tuple[str | None, int]:
    """Parse ``(host, port)`` from a ``bolt://`` / ``neo4j://`` / ``postgresql://`` URI.

    Falls back to the scheme's default port (7687 for bolt/neo4j, else 5432). Returns
    ``(None, 0)`` when no host can be parsed (so the caller does not block on a junk URI).
    """
    parsed = urlparse(uri)
    if not parsed.hostname:
        return None, 0
    default = 7687 if parsed.scheme.startswith(("bolt", "neo4j")) else 5432
    return parsed.hostname, parsed.port or default


def tcp_refused(host: str, port: int, timeout: float = 1.5) -> bool:
    """True iff a TCP connect to ``host:port`` is actively refused (the store isn't up).

    Ambiguous failures (timeout, DNS, network) return ``False`` -- never block on uncertainty.
    """
    import socket

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return False
    except ConnectionRefusedError:
        return True
    except OSError:
        return False


def store_unreachable(
    uri: str, *, label: str, fix: str, refused: Callable[[str, int], bool] = tcp_refused
) -> str | None:
    """An actionable message if ``uri``'s store is definitively down, else ``None``."""
    host, port = host_port(uri)
    if host and refused(host, port):
        return f"{label} is not reachable at {host}:{port} (connection refused). {fix}"
    return None


def workup_preflight(
    env: dict[str, str],
    *,
    with_sql: bool,
    with_semantic: bool,
    refused: Callable[[str, int], bool] = tcp_refused,
) -> str | None:
    """The first store that the run needs but cannot reach, as an actionable message, or ``None``.

    Always checks Neo4j (the graph store every workup uses); checks Postgres only when the run
    will touch the relational/semantic legs (``--sql`` / ``--semantic``).
    """
    msg = store_unreachable(
        env.get("NEO4J_URI", _NEO4J_DEFAULT),
        label="Neo4j (the graph store)",
        fix=(
            "Start it: docker compose -f infra/neo4j/docker-compose.yml up -d, "
            "then seed it with infra/neo4j/seed.cypher."
        ),
        refused=refused,
    )
    if msg or not (with_sql or with_semantic):
        return msg
    return store_unreachable(
        env.get("DATABASE_URI", _PG_DEFAULT),
        label="Postgres (the relational/semantic store)",
        fix="Start it: docker compose -f infra/postgres/docker-compose.yml up -d.",
        refused=refused,
    )
