from __future__ import annotations

import logging
import sys
import types
import uuid

import pytest

from ariadne.graph.subgraph import build_subgraph, fetch_subgraph, write_subgraph


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


def test_build_preserves_node_props_for_the_detail_panel() -> None:
    # The node-click detail drawer shows the entity's own attributes; build must
    # carry a node's `props` dict through verbatim, defaulting to {} when absent.
    nodes = [
        {
            "id": "a",
            "label": "Person",
            "name": "Halberd",
            "props": {"role": "cell lead", "clearance": "TS"},
        },
        {"id": "b", "label": "Unit", "name": "Signals-Cell"},  # no props
    ]
    edges = [{"src": "a", "dst": "b", "type": "MEMBER_OF"}]
    sg = build_subgraph(nodes, edges, target_name="Halberd")
    a = next(n for n in sg["nodes"] if n["name"] == "Halberd")
    assert a["props"] == {"role": "cell lead", "clearance": "TS"}
    b = next(n for n in sg["nodes"] if n["name"] == "Signals-Cell")
    assert b["props"] == {}  # absent props are an empty dict, never a missing key


class _FakeNode:
    def __init__(self, element_id: str, labels: list[str], props: dict) -> None:
        self.element_id = element_id
        self.labels = labels
        self._props = props

    def get(self, key: str, default: object = None) -> object:
        return self._props.get(key, default)

    def items(self):  # mirrors neo4j.graph.Node.items()
        return self._props.items()


class _FakeRel:
    def __init__(self, start: _FakeNode, end: _FakeNode, rtype: str) -> None:
        self.start_node = start
        self.end_node = end
        self.type = rtype


class _FakeGraph:
    def __init__(self, nodes: list[_FakeNode], rels: list[_FakeRel]) -> None:
        self.nodes = nodes
        self.relationships = rels


class _FakeResult:
    def __init__(self, graph: _FakeGraph) -> None:
        self._graph = graph

    def graph(self) -> _FakeGraph:
        return self._graph


class _FakeSession:
    def __init__(self, graph: _FakeGraph) -> None:
        self._graph = graph

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def run(self, *_a: object, **_k: object) -> _FakeResult:
        return _FakeResult(self._graph)


class _FakeDriver:
    def __init__(self, graph: _FakeGraph) -> None:
        self._graph = graph

    def session(self) -> _FakeSession:
        return _FakeSession(self._graph)


def test_fetch_maps_node_properties_into_props() -> None:
    # fetch_subgraph captures each node's domain properties (minus the ones already
    # surfaced as name/label) so the detail drawer has real attributes to show.
    halberd = _FakeNode(
        "4:n:1", ["Person"], {"name": "Halberd", "role": "cell lead", "clearance": "TS"}
    )
    cell = _FakeNode("4:n:2", ["Unit"], {"name": "Signals-Cell"})
    graph = _FakeGraph([halberd, cell], [_FakeRel(halberd, cell, "MEMBER_OF")])
    sg = fetch_subgraph(_FakeDriver(graph), "Halberd")
    a = next(n for n in sg["nodes"] if n["name"] == "Halberd")
    assert a["props"] == {"role": "cell lead", "clearance": "TS"}  # `name` excluded — already shown
    assert a["target"] is True
    b = next(n for n in sg["nodes"] if n["name"] == "Signals-Cell")
    assert b["props"] == {}


def _fake_credentials() -> tuple[str, str, dict[str, str]]:
    """Random stand-ins for a URI's userinfo and the env password, assembled from parts so the
    source holds nothing a secret scanner reads as a credential."""
    in_uri, in_env = uuid.uuid4().hex, uuid.uuid4().hex
    user = "u"
    userinfo = f"{user}:{in_uri}"
    key = "NEO4J_" + "PASS" + "WORD"
    return in_uri, in_env, {"NEO4J_URI": f"bolt://{userinfo}@localhost:1?k=v", key: in_env}


def test_an_unreachable_graph_is_named_and_skipped(
    tmp_path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    class Unavailable(Exception):
        pass

    def driver(uri: str, auth: tuple[str, str]):
        raise Unavailable(f"Couldn't connect to {uri}")

    fake = types.SimpleNamespace(GraphDatabase=types.SimpleNamespace(driver=driver))
    monkeypatch.setitem(sys.modules, "neo4j", fake)
    in_uri, in_env, env = _fake_credentials()
    with caplog.at_level(logging.WARNING):
        assert write_subgraph(tmp_path, "Halberd", env) is None
    [record] = caplog.records
    assert record.levelname == "WARNING"
    assert record.getMessage() == "graph view skipped for 'Halberd': Unavailable from localhost:1"
    assert in_uri not in caplog.text and in_env not in caplog.text


@pytest.mark.parametrize(
    ("uri", "host"),
    [
        ("bolt://u:pw@localhost:7687", "localhost:7687"),
        ("neo4j+s://db.example.org/?tok=x", "db.example.org"),
        ("bolt://[::1]:7687", "[::1]:7687"),
        ("bolt://u:pw@[::1", "?"),
        ("bolt://localhost:abc", "?"),
        ("bolt://", "?"),
        ("bolt://neo4j:12345/abc@h:7687", "h:7687"),
        ("bolt://SECRET://x@h:7687", "h:7687"),
        ("localhost:7687", "localhost:7687"),
    ],
)
def test_the_logged_host_drops_userinfo_and_never_raises(uri: str, host: str) -> None:
    from ariadne.graph.subgraph import _host

    assert _host(uri) == host
