"""Structured neighborhood subgraph for the interactive report (ADR-0017 follow-on).

A workup persists ``subgraph.json`` — the real entity network it traversed (nodes +
typed relationships around the target) — so the report can draw the analytic graph
(Halberd → Signals-Cell → Compound-Alpha → Talon), not just the evidence fan. The
subgraph comes from a deterministic bounded neighborhood query (no fragile parsing
of free-text query results); ``build_subgraph`` is the pure, testable core.
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


def build_subgraph(
    nodes: Iterable[dict], edges: Iterable[dict], *, target_name: str | None = None
) -> dict[str, list[dict]]:
    """Dedupe nodes/edges and flag the target node.

    Nodes are ``{id, label, name}``; edges ``{src, dst, type}``. Edges whose
    endpoints are not in the node set are dropped (no dangling links). The node
    whose ``name`` matches ``target_name`` is flagged ``target: True``.
    """
    seen_nodes: dict[str, dict] = {}
    for n in nodes:
        nid = str(n.get("id", ""))
        if nid and nid not in seen_nodes:
            name = n.get("name") or n.get("label") or nid
            seen_nodes[nid] = {
                "id": nid,
                "label": n.get("label") or "Node",
                "name": name,
                "target": target_name is not None and name == target_name,
            }
    seen_edges: dict[tuple[str, str, str], dict] = {}
    for e in edges:
        src, dst, typ = str(e.get("src", "")), str(e.get("dst", "")), str(e.get("type", ""))
        if src in seen_nodes and dst in seen_nodes:
            seen_edges.setdefault((src, dst, typ), {"src": src, "dst": dst, "type": typ})
    return {"nodes": list(seen_nodes.values()), "edges": list(seen_edges.values())}


def fetch_subgraph(driver: Any, entity: str, *, hops: int = 2, limit: int = 80) -> dict:
    """Run a bounded neighborhood query around ``entity`` and return a subgraph dict.

    Matches the entity by ``name`` / ``alias`` / ``id`` / aliases membership, expands
    up to ``hops`` undirected, and maps the driver's graph view to canonical
    nodes/edges. Returns ``{"nodes": [], "edges": []}`` if the entity isn't found.
    """
    query = (
        "MATCH (n) WHERE n.name = $e OR n.alias = $e OR n.id = $e "
        "OR (n.aliases IS NOT NULL AND $e IN n.aliases) WITH n LIMIT 1 "
        f"MATCH p=(n)-[*1..{hops}]-(m) RETURN p LIMIT $lim"
    )
    with driver.session() as session:
        result = session.run(query, e=entity, lim=limit)
        graph = result.graph()
        nodes = [
            {
                "id": n.element_id,
                "label": next(iter(n.labels), "Node"),
                "name": n.get("name") or n.get("id") or next(iter(n.labels), "Node"),
            }
            for n in graph.nodes
        ]
        edges = [
            {"src": r.start_node.element_id, "dst": r.end_node.element_id, "type": r.type}
            for r in graph.relationships
        ]
    return build_subgraph(nodes, edges, target_name=entity)


def write_subgraph(out_dir: str | Path, entity: str, env: Mapping[str, str]) -> Path | None:
    """Best-effort: query the entity's neighborhood and persist ``subgraph.json``.

    Optional — returns ``None`` (and writes nothing) if neo4j isn't installed, the
    graph is unreachable, or the entity has no neighborhood. Never raises, so it
    cannot fail a workup.
    """
    try:
        from neo4j import GraphDatabase
    except ImportError:
        return None
    uri = env.get("NEO4J_URI", "bolt://localhost:7687")
    auth = (env.get("NEO4J_USERNAME", "neo4j"), env.get("NEO4J_PASSWORD", "password"))
    sg: dict = {"nodes": [], "edges": []}
    # graph view is optional; never break a workup over it
    with contextlib.suppress(Exception), GraphDatabase.driver(uri, auth=auth) as driver:
        sg = fetch_subgraph(driver, entity)
    if not sg["nodes"]:
        return None
    path = Path(out_dir) / "subgraph.json"
    path.write_text(json.dumps(sg, indent=2), encoding="utf-8")
    return path
