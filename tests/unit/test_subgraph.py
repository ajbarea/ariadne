from __future__ import annotations

from ariadne.graph.subgraph import build_subgraph


def test_build_dedupes_nodes_and_edges_and_flags_target() -> None:
    nodes = [
        {"id": "a", "label": "Person", "name": "Halberd"},
        {"id": "b", "label": "Unit", "name": "Signals-Cell"},
        {"id": "a", "label": "Person", "name": "Halberd"},  # dup (paths revisit nodes)
    ]
    edges = [
        {"src": "a", "dst": "b", "type": "MEMBER_OF"},
        {"src": "a", "dst": "b", "type": "MEMBER_OF"},  # dup
    ]
    sg = build_subgraph(nodes, edges, target_name="Halberd")
    assert len(sg["nodes"]) == 2
    assert len(sg["edges"]) == 1
    target = next(n for n in sg["nodes"] if n["name"] == "Halberd")
    assert target["target"] is True
    assert next(n for n in sg["nodes"] if n["name"] == "Signals-Cell")["target"] is False


def test_build_drops_edges_with_unknown_endpoints() -> None:
    nodes = [{"id": "a", "label": "Person", "name": "X"}]
    edges = [{"src": "a", "dst": "ghost", "type": "REL"}]
    sg = build_subgraph(nodes, edges, target_name="X")
    assert sg["edges"] == []  # an edge to a node not in the set is dropped, not dangling
