# Phase A — Dataset Abstraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce the dataset-agnostic seam — canonical schema, adapter contract, registry, graph indexer — and refactor the existing synthetic graph into the first adapter, with no runtime regression and no new external data.

**Architecture:** Four canonical record types (`Entity`/`Relationship`/`Document`/`Attribute`) are the contract; a `DatasetAdapter` Protocol + `DATASETS` registry select a corpus by name; a pure indexer turns canonical records into idempotent store-load statements. Phase A delivers the seam + a `SyntheticAdapter` that reproduces today's seed graph; live store-writing and the Enron/Avocado adapters are Phases B/C.

**Tech Stack:** Python 3.14, `uv`, `ruff`, `pytest`. Mirrors existing idioms (`evaluation/needle.py` `FIXTURES` registry, frozen dataclasses, `from __future__ import annotations`).

> **Commits:** AJ batches commits at session end. Each task's commit step is a logical checkpoint; staging (`git add`) is what matters — AJ may squash the batch. Run `make lint && uv run python -m pytest tests/unit -q` is the gate (note: `uv run python -m pytest`, not `uv run pytest`).

---

### Task 1: Canonical schema

**Files:**
- Create: `src/ariadne/datasets/__init__.py` (empty)
- Create: `src/ariadne/datasets/canonical.py`
- Test: `tests/unit/test_canonical_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_canonical_schema.py
from __future__ import annotations

from ariadne.datasets.canonical import (
    SCHEMA_VERSION,
    Attribute,
    Document,
    Entity,
    Relationship,
)


def test_entity_holds_identity_and_open_attributes() -> None:
    e = Entity(id="person:Halberd", type="person", name="Halberd",
               aliases=("H1",), attributes={"clearance": "SECRET"})
    assert e.id == "person:Halberd"
    assert e.attributes["clearance"] == "SECRET"


def test_relationship_references_entity_ids() -> None:
    r = Relationship(src="person:Halberd", dst="unit:Signals-Cell",
                     type="MEMBER_OF", attributes={"role": "Lead"})
    assert r.src == "person:Halberd"
    assert r.type == "MEMBER_OF"


def test_document_carries_text_metadata_and_sources() -> None:
    d = Document(id="email:1", text="hello", source_entity_ids=("person:Halberd",),
                 metadata={"subject": "hi"}, modality="email_body")
    assert d.modality == "email_body"
    assert "person:Halberd" in d.source_entity_ids


def test_attribute_is_a_per_entity_fact() -> None:
    a = Attribute(entity_id="person:Halberd", key="role", value="Signals Lead")
    assert a.entity_id == "person:Halberd"


def test_schema_version_is_set() -> None:
    assert isinstance(SCHEMA_VERSION, int) and SCHEMA_VERSION >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/test_canonical_schema.py -q`
Expected: FAIL — `ModuleNotFoundError: ariadne.datasets.canonical`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ariadne/datasets/canonical.py
"""Canonical schema — the dataset-agnostic contract every adapter maps to.

Kept deliberately minimal (avoid the canonical "god model"): dataset-specific
fields live in the open ``attributes``/``metadata`` dicts, never as new core
fields. Each record maps to one store (see the indexer):
Entity/Relationship -> graph, Document -> full-text+vector(text)+relational(meta),
Attribute -> relational row.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Entity:
    id: str  # canonical, e.g. "person:Halberd"
    type: str  # person | org | unit | site | topic ...
    name: str
    aliases: tuple[str, ...] = ()
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Relationship:
    src: str  # Entity.id
    dst: str  # Entity.id
    type: str  # MEMBER_OF | EMAILED | CO_LOCATED ...
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Document:
    id: str
    text: str
    source_entity_ids: tuple[str, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)
    modality: str = "text"


@dataclass(frozen=True)
class Attribute:
    entity_id: str
    key: str
    value: str


Canonical = Union[Entity, Relationship, Document, Attribute]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/unit/test_canonical_schema.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/ariadne/datasets/__init__.py src/ariadne/datasets/canonical.py tests/unit/test_canonical_schema.py
git commit -m "feat(datasets): canonical schema (Entity/Relationship/Document/Attribute)"
```

---

### Task 2: Adapter contract + registry

**Files:**
- Create: `src/ariadne/datasets/base.py`
- Test: `tests/unit/test_dataset_registry.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_dataset_registry.py
from __future__ import annotations

import pytest

from ariadne.datasets.base import DATASETS, get_adapter, register
from ariadne.datasets.canonical import Entity


class _FakeAdapter:
    name = "fake"
    entity_type = "person"
    access = "public"

    def load(self):
        yield Entity(id="person:X", type="person", name="X")

    def eval_fixtures(self):
        return []


def test_register_then_get_round_trips() -> None:
    register(_FakeAdapter())
    assert "fake" in DATASETS
    assert get_adapter("fake").entity_type == "person"


def test_unknown_dataset_raises_keyerror_listing_known() -> None:
    with pytest.raises(KeyError):
        get_adapter("nope")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/test_dataset_registry.py -q`
Expected: FAIL — `ModuleNotFoundError: ariadne.datasets.base`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ariadne/datasets/base.py
"""Dataset adapter contract + registry.

A dataset is added by implementing ``DatasetAdapter`` and registering it. The
agent, connectors, skill, and eval harness never change — only an adapter does.
Mirrors the ``FIXTURES`` registry idiom in ``evaluation/needle.py``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal, Protocol, runtime_checkable

from ariadne.datasets.canonical import Canonical
from ariadne.evaluation.needle import NeedleFixture


@runtime_checkable
class DatasetAdapter(Protocol):
    name: str
    entity_type: str
    access: Literal["public", "restricted"]

    def load(self) -> Iterable[Canonical]: ...

    def eval_fixtures(self) -> list[NeedleFixture]: ...


DATASETS: dict[str, DatasetAdapter] = {}


def register(adapter: DatasetAdapter) -> None:
    DATASETS[adapter.name] = adapter


def get_adapter(name: str) -> DatasetAdapter:
    try:
        return DATASETS[name]
    except KeyError as exc:
        raise KeyError(f"unknown dataset {name!r}; known: {sorted(DATASETS)}") from exc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/unit/test_dataset_registry.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/ariadne/datasets/base.py tests/unit/test_dataset_registry.py
git commit -m "feat(datasets): DatasetAdapter protocol + registry"
```

---

### Task 3: Graph indexer (canonical → idempotent Cypher)

**Files:**
- Create: `src/ariadne/datasets/indexer.py`
- Test: `tests/unit/test_indexer.py`

Phase A scope: Entity + Relationship → graph Cypher. `Document`/`Attribute`
(full-text / pgvector / relational) indexing is Phase B and is intentionally
skipped here.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_indexer.py
from __future__ import annotations

from ariadne.datasets.canonical import Entity, Relationship
from ariadne.datasets.indexer import index_graph


def test_entity_becomes_idempotent_merge_keyed_on_id() -> None:
    cy = index_graph([Entity(id="person:Halberd", type="person", name="Halberd",
                             attributes={"alias": "H1"})])
    assert any("MERGE" in s and "person:Halberd" in s for s in cy)
    assert any(":Person" in s for s in cy)  # type -> title-case label
    assert all("CREATE " not in s for s in cy)  # idempotent, not CREATE


def test_relationship_matches_endpoints_by_id_then_merges_edge() -> None:
    cy = index_graph([Relationship(src="person:Halberd", dst="unit:Signals-Cell",
                                   type="MEMBER_OF", attributes={"role": "Lead"})])
    joined = "\n".join(cy)
    assert "person:Halberd" in joined and "unit:Signals-Cell" in joined
    assert "MERGE" in joined and "MEMBER_OF" in joined


def test_documents_and_attributes_are_skipped_in_phase_a() -> None:
    from ariadne.datasets.canonical import Attribute, Document
    cy = index_graph([
        Document(id="d1", text="x"),
        Attribute(entity_id="person:X", key="k", value="v"),
    ])
    assert cy == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/test_indexer.py -q`
Expected: FAIL — `ModuleNotFoundError: ariadne.datasets.indexer`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ariadne/datasets/indexer.py
"""Canonical records -> store-load statements.

Pure transform (no DB connection), so it is fully unit-testable; Phase B wires
its output to live stores during ingestion. Phase A covers the graph
(Entity/Relationship); Document/Attribute store-loading lands in Phase B.
"""

from __future__ import annotations

from collections.abc import Iterable

from ariadne.datasets.canonical import Canonical, Entity, Relationship


def _label(entity_type: str) -> str:
    # "person" -> "Person"; matches the existing seed's typed labels.
    return entity_type[:1].upper() + entity_type[1:]


def _props(attributes: dict[str, str]) -> str:
    # Deterministic, sorted; values are synthetic/fictional in Phase A.
    return ", ".join(f"n.{k} = {v!r}" for k, v in sorted(attributes.items()))


def index_graph(records: Iterable[Canonical]) -> list[str]:
    """Return idempotent Cypher (MERGE) for Entity/Relationship records only."""
    out: list[str] = []
    for rec in records:
        if isinstance(rec, Entity):
            stmt = f"MERGE (n:{_label(rec.type)} {{id: {rec.id!r}}}) SET n.name = {rec.name!r}"
            if rec.attributes:
                stmt += ", " + _props(rec.attributes)
            out.append(stmt)
        elif isinstance(rec, Relationship):
            stmt = (
                f"MATCH (a {{id: {rec.src!r}}}), (b {{id: {rec.dst!r}}}) "
                f"MERGE (a)-[r:{rec.type}]->(b)"
            )
            if rec.attributes:
                stmt += " SET " + ", ".join(
                    f"r.{k} = {v!r}" for k, v in sorted(rec.attributes.items())
                )
            out.append(stmt)
        # Document / Attribute: Phase B.
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/unit/test_indexer.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/ariadne/datasets/indexer.py tests/unit/test_indexer.py
git commit -m "feat(datasets): pure graph indexer (canonical -> idempotent Cypher)"
```

---

### Task 4: SyntheticAdapter (reproduce the seed graph)

**Files:**
- Create: `src/ariadne/datasets/synthetic.py`
- Test: `tests/unit/test_synthetic_adapter.py`

Source of truth for the records: `infra/neo4j/seed.cypher` (4 Units, 1 Site, 4
Persons; REPORTS_TO / MEMBER_OF / COMMUNICATES_WITH / CO_LOCATED edges; the
planted Halberd↔Compound-Alpha↔Wren co-location path).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_synthetic_adapter.py
from __future__ import annotations

from ariadne.datasets.base import get_adapter
from ariadne.datasets.canonical import Entity, Relationship
from ariadne.datasets.indexer import index_graph
from ariadne.datasets.synthetic import SyntheticAdapter
import ariadne.datasets.synthetic  # noqa: F401  (import registers it)


def test_adapter_metadata() -> None:
    a = SyntheticAdapter()
    assert a.name == "synthetic"
    assert a.entity_type == "person"
    assert a.access == "public"


def test_load_yields_the_planted_needle_entities_and_edges() -> None:
    recs = list(SyntheticAdapter().load())
    entities = {r.name for r in recs if isinstance(r, Entity)}
    assert {"Halberd", "Wren", "Signals-Cell", "Logistics-Cell", "Compound-Alpha"} <= entities
    rels = {(r.type) for r in recs if isinstance(r, Relationship)}
    assert {"MEMBER_OF", "CO_LOCATED"} <= rels


def test_indexing_load_emits_the_colocation_bridge() -> None:
    cy = "\n".join(index_graph(SyntheticAdapter().load()))
    assert "Compound-Alpha" in cy and "CO_LOCATED" in cy


def test_registered_in_the_registry_on_import() -> None:
    assert get_adapter("synthetic").name == "synthetic"


def test_eval_fixtures_are_the_known_needles() -> None:
    names = {f.entity for f in SyntheticAdapter().eval_fixtures()}
    assert "Halberd" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/test_synthetic_adapter.py -q`
Expected: FAIL — `ModuleNotFoundError: ariadne.datasets.synthetic`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ariadne/datasets/synthetic.py
"""The synthetic org-graph dataset as the first adapter.

Mirrors infra/neo4j/seed.cypher so today's behaviour flows through the new
adapter seam. No external data; access is public.
"""

from __future__ import annotations

from collections.abc import Iterable

from ariadne.datasets.base import register
from ariadne.datasets.canonical import Canonical, Entity, Relationship
from ariadne.evaluation.needle import HALBERD_FIXTURE, WREN_TIE_FIXTURE, NeedleFixture

_UNITS = [
    ("Directorate-HQ", {"echelon": "1"}),
    ("Operations-Wing", {"echelon": "2"}),
    ("Signals-Cell", {"echelon": "3"}),
    ("Logistics-Cell", {"echelon": "3"}),
]
_PERSONS = [("Halberd", "H1"), ("Wren", "W4"), ("Talon", "T2"), ("Osprey", "O7")]
_RELS = [
    ("unit:Operations-Wing", "unit:Directorate-HQ", "REPORTS_TO", {}),
    ("unit:Signals-Cell", "unit:Operations-Wing", "REPORTS_TO", {}),
    ("unit:Logistics-Cell", "unit:Operations-Wing", "REPORTS_TO", {}),
    ("person:Halberd", "unit:Signals-Cell", "MEMBER_OF", {"role": "Lead"}),
    ("person:Talon", "unit:Signals-Cell", "MEMBER_OF", {"role": "Analyst"}),
    ("person:Wren", "unit:Logistics-Cell", "MEMBER_OF", {"role": "Lead"}),
    ("person:Osprey", "unit:Logistics-Cell", "MEMBER_OF", {"role": "Driver"}),
    ("person:Halberd", "person:Talon", "COMMUNICATES_WITH", {"channel": "voice"}),
    ("unit:Signals-Cell", "site:Compound-Alpha", "CO_LOCATED", {}),
    ("unit:Logistics-Cell", "site:Compound-Alpha", "CO_LOCATED", {}),
]


class SyntheticAdapter:
    name = "synthetic"
    entity_type = "person"
    access = "public"

    def load(self) -> Iterable[Canonical]:
        for name, attrs in _UNITS:
            yield Entity(id=f"unit:{name}", type="unit", name=name, attributes=attrs)
        yield Entity(id="site:Compound-Alpha", type="site", name="Compound-Alpha")
        for name, alias in _PERSONS:
            yield Entity(id=f"person:{name}", type="person", name=name,
                         aliases=(alias,), attributes={"alias": alias})
        for src, dst, rtype, attrs in _RELS:
            yield Relationship(src=src, dst=dst, type=rtype, attributes=attrs)

    def eval_fixtures(self) -> list[NeedleFixture]:
        return [HALBERD_FIXTURE, WREN_TIE_FIXTURE]


register(SyntheticAdapter())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/unit/test_synthetic_adapter.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/ariadne/datasets/synthetic.py tests/unit/test_synthetic_adapter.py
git commit -m "feat(datasets): synthetic adapter reproducing the seed graph"
```

---

### Task 5: Wire `--dataset` into the CLI

**Files:**
- Modify: `src/ariadne/cli.py` (imports; `parse_args` workup parser; `main`/`run_workup` signature)
- Test: `tests/unit/test_cli_dataset_flag.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_cli_dataset_flag.py
from __future__ import annotations

import pytest

from ariadne.cli import parse_args


def test_workup_defaults_to_synthetic_dataset() -> None:
    args = parse_args(["workup", "Halberd"])
    assert args.dataset == "synthetic"


def test_workup_accepts_a_known_dataset() -> None:
    args = parse_args(["workup", "Halberd", "--dataset", "synthetic"])
    assert args.dataset == "synthetic"


def test_unknown_dataset_is_rejected_by_argparse() -> None:
    with pytest.raises(SystemExit):
        parse_args(["workup", "Halberd", "--dataset", "nope"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/test_cli_dataset_flag.py -q`
Expected: FAIL — `AttributeError: 'Namespace' object has no attribute 'dataset'`

- [ ] **Step 3: Write minimal implementation**

In `src/ariadne/cli.py`, add the import (with the other `ariadne.*` imports near line 27):

```python
from ariadne.datasets.base import DATASETS
import ariadne.datasets.synthetic  # noqa: F401  (registers the synthetic adapter)
```

In `parse_args`, add to the `wk` (workup) parser after the `--sql` argument (line 58):

```python
    wk.add_argument(
        "--dataset",
        choices=sorted(DATASETS),
        default="synthetic",
        help="Which dataset to work up (default: synthetic).",
    )
```

Change `run_workup`'s signature to thread the dataset through, and validate it:

```python
async def run_workup(
    entity: str, out_root: str, env: dict[str, str], *, with_sql: bool = False,
    dataset: str = "synthetic",
) -> int:
    from ariadne.datasets.base import get_adapter
    get_adapter(dataset)  # raises KeyError on unknown; synthetic uses the seeded graph
    ledger = ProvenanceLedger()
    options = build_options(ledger=ledger, env=env, with_sql=with_sql)
    # ... rest unchanged ...
```

Update the `main` call site (line 173):

```python
    return asyncio.run(
        run_workup(args.entity, args.out, dict(os.environ),
                   with_sql=args.sql, dataset=args.dataset)
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/unit/test_cli_dataset_flag.py -q`
Expected: PASS (3 passed)

Run the full unit suite to confirm no regression:
Run: `uv run python -m pytest tests/unit tests/test_smoke.py -q`
Expected: PASS (all prior tests + the new ones)

- [ ] **Step 5: Commit**

```bash
git add src/ariadne/cli.py tests/unit/test_cli_dataset_flag.py
git commit -m "feat(cli): --dataset flag (default synthetic) wired to the registry"
```

---

### Task 6: ADR-0006 + docs update + concision pass

**Files:**
- Create: `docs/architecture/decisions/0006-dataset-agnostic-pipeline.md`
- Modify: `docs/architecture/decisions/index.md` (add the row)
- Modify: `zensical.toml` (add 0006 to the Decisions nav)
- Modify: `docs/architecture/index.md` (add a tight "Datasets" subsection; trim the "To be written" block)
- Modify: `IMPL.md` (note Phase A shipped), `ROADMAP.md` (multi-dataset expansion entry)
- Modify: `docs/superpowers/specs/2026-06-03-multi-dataset-pipeline-design.md` (renumber: hybrid retrieval → ADR-0007, governance → ADR-0008, since 0006 is now the dataset abstraction)
- Concision pass: `docs/overview.md`, `docs/research/index.md`, `docs/architecture/index.md` — tighten verbose paragraphs to 1-2 sentences each without dropping facts.

- [ ] **Step 1: Write ADR-0006** (MADR format, matching the existing five records): Status Accepted; Context = multi-dataset demo feedback; Decision drivers = extensibility, governance choke point, no N×M coupling; Considered options = canonical+adapter / per-dataset bespoke / framework-as-architecture; Decision = canonical schema + adapter + registry; Consequences = adding a dataset touches one adapter; sources = the two canonical-data-model links from the spec.

- [ ] **Step 2: Add the registry row** to `docs/architecture/decisions/index.md`:

```markdown
| [0006](0006-dataset-agnostic-pipeline.md) | Dataset-agnostic pipeline (canonical schema + adapters) | Accepted |
```

- [ ] **Step 3: Add 0006 to the Decisions nav** in `zensical.toml` (after the 0005 line).

- [ ] **Step 4: Run the docs build to verify nav + links resolve**

Run: `uv run --with zensical zensical build`
Expected: "No issues found"

- [ ] **Step 5: Apply the concision pass** to the listed docs (tighten, keep every fact), then re-run the build.

Run: `uv run --with zensical zensical build`
Expected: "No issues found"

- [ ] **Step 6: Final gate + commit**

```bash
make lint
uv run python -m pytest tests/unit tests/test_smoke.py -q
git add docs/ zensical.toml IMPL.md ROADMAP.md
git commit -m "docs(datasets): ADR-0006 dataset abstraction; concision pass"
```

---

## Phase A done (all true)

1. `ariadne workup <entity> --dataset synthetic` parses and runs as today (no regression); unknown `--dataset` is rejected.
2. `SyntheticAdapter.load()` reproduces the seed graph as canonical records; `index_graph` turns them into idempotent Cypher including the planted co-location bridge.
3. Adding a dataset would touch only a new adapter file + its fixtures.
4. `make lint` + `uv run python -m pytest tests/unit tests/test_smoke.py -q` green; `zensical build` clean.
5. ADR-0006 written and in the nav.

## Next plans (after A lands, against real interfaces)

- **Phase B:** Enron HF adapter + the hybrid (full-text + pgvector) retrieval connector + indexer `Document`/`Attribute` store-loading → ADR-0007.
- **Phase C:** Avocado `restricted` adapter + access-control governance → a future governance ADR.
```
