from __future__ import annotations

from ariadne.datasets.load import graph_statements
from ariadne.datasets.synthetic import SyntheticAdapter


def test_graph_statements_emit_uniqueness_constraints_per_label() -> None:
    stmts = graph_statements(list(SyntheticAdapter().load()))
    constraints = [s for s in stmts if "CONSTRAINT" in s]
    assert any(":Person" in c and "id IS UNIQUE" in c for c in constraints)
    assert any(":Unit" in c for c in constraints) and any(":Site" in c for c in constraints)


def test_graph_statements_put_constraints_before_merges() -> None:
    stmts = graph_statements(list(SyntheticAdapter().load()))
    first_merge = next(i for i, s in enumerate(stmts) if s.startswith("MERGE"))
    assert all("CONSTRAINT" not in s for s in stmts[first_merge:])
