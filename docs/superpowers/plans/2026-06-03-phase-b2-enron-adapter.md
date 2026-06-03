# Phase B2 — Enron Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A real-data dataset adapter — map the `corbt/enron-emails` corpus to canonical records (deterministic header→graph, body→document) and feed it through the B1 pipeline, with an eval needle on a documented, non-obvious tie.

**Architecture:** A pure `map_messages(rows)` transform (rows → canonical Entity/Relationship/Document) stays unit-testable with fabricated rows; `EnronAdapter.load()` streams the corpus from Hugging Face (lazy `datasets` import, bounded to the `kaminski-v` mailbox), calls `map_messages`, and registers itself. No LLM (D3). The semantic/pgvector leg is still B3.

**Demo subject (decided):** Vince Kaminski (`vince.kaminski@enron.com`, mailbox `kaminski-v`) — Head of Quantitative Modeling, the documented internal risk-warner; ~14K emails. **Eval needle:** his cross-account tie to the personal `vkaminski@aol.com` address (~1,059 forwarded work emails) — a real "same person, two identities" non-obvious connection.

**Tech Stack:** Python 3.14, `uv`, `ruff`, `pytest`; HF `datasets` behind an optional `data` extra (lazy-imported, streaming). ENV: pytest is `uv run python -m pytest …` (NOT `uv run pytest`). The live HF load test needs `uv sync --extra data` + network.

> **Grounding (June 2026, verified):** `corbt/enron-emails` schema is fully structured — `message_id`, `subject`, `from` (str), `to`/`cc`/`bcc` (`list[str]`), `date` (timestamp), `body` (str), `file_name` (str, mailbox-prefixed) — so header→graph is deterministic; HF `datasets` is the standard loader, `streaming=True` avoids a full download.

> **Commits:** plain messages, NO Co-Authored-By / "Generated with" / 🤖 lines. Gate: `make lint && uv run python -m pytest tests/unit tests/test_smoke.py -q`.

---

### Task 1: `data` extra + pure `map_messages` transform

**Files:**
- Modify: `pyproject.toml` (add `[project.optional-dependencies] data = ["datasets>=3"]`), `uv.lock`
- Create: `src/ariadne/datasets/enron.py` (mapping only this task; the adapter class lands in Task 2)
- Test: `tests/unit/test_enron_mapping.py`

- [ ] **Step 1: Add the extra.** In `pyproject.toml` under `[project.optional-dependencies]`, add `data = ["datasets>=3"]`. Run `uv lock` to update `uv.lock`. (Do NOT `uv sync --extra data` yet — Task 1 is hermetic and must not import `datasets`.)

- [ ] **Step 2: Write the failing test** (`tests/unit/test_enron_mapping.py`):

```python
from __future__ import annotations

from ariadne.datasets.canonical import Document, Entity, Relationship
from ariadne.datasets.enron import map_messages

_ROWS = [
    {"message_id": "m1", "from": "vince.kaminski@enron.com",
     "to": ["shirley.crenshaw@enron.com"], "cc": [], "subject": "models",
     "date": "2001-05-14T23:39:00", "body": "see attached", "file_name": "kaminski-v/sent/1."},
    {"message_id": "m2", "from": "vince.kaminski@enron.com",
     "to": ["vkaminski@aol.com"], "cc": [], "subject": "fwd",
     "date": "2001-05-15T08:00:00", "body": "forwarding to myself", "file_name": "kaminski-v/sent/2."},
    {"message_id": "m3", "from": "vince.kaminski@enron.com",
     "to": ["vkaminski@aol.com"], "cc": [], "subject": "fwd2",
     "date": "2001-05-16T08:00:00", "body": "again", "file_name": "kaminski-v/sent/3."},
]


def test_addresses_become_person_entities() -> None:
    recs = list(map_messages(_ROWS))
    people = {r.name for r in recs if isinstance(r, Entity) and r.type == "person"}
    assert "vince.kaminski@enron.com" in people and "vkaminski@aol.com" in people


def test_emailed_edges_are_aggregated_with_a_count() -> None:
    recs = list(map_messages(_ROWS))
    aol = [r for r in recs if isinstance(r, Relationship) and r.type == "EMAILED"
           and r.dst == "person:vkaminski@aol.com"]
    assert len(aol) == 1  # two messages collapse to one aggregated edge
    assert aol[0].attributes["count"] == "2"
    assert aol[0].src == "person:vince.kaminski@enron.com"


def test_bodies_become_email_documents() -> None:
    recs = list(map_messages(_ROWS))
    docs = [r for r in recs if isinstance(r, Document)]
    assert len(docs) == 3
    assert docs[0].modality == "email_body"
    assert docs[0].metadata["subject"] == "models"


def test_empty_addresses_are_skipped() -> None:
    rows = [{"message_id": "x", "from": "", "to": [""], "cc": [], "subject": "",
             "date": "", "body": "b", "file_name": "f"}]
    recs = list(map_messages(rows))
    assert not any(isinstance(r, Entity) for r in recs)
    assert not any(isinstance(r, Relationship) for r in recs)
```

- [ ] **Step 3: run** → FAIL (ModuleNotFoundError / no `map_messages`).

- [ ] **Step 4: Implement** `src/ariadne/datasets/enron.py` (mapping only):

```python
"""Enron email corpus (`corbt/enron-emails`) as a dataset adapter.

Deterministic header→graph + body→document mapping — no LLM (ADR/spec D3).
``map_messages`` is a pure transform (fabricated rows in tests); the adapter
class streams the real corpus in Task 2.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from ariadne.datasets.canonical import Canonical, Document, Entity, Relationship


def _norm(addr: str) -> str:
    return (addr or "").strip().lower()


def _person_id(addr: str) -> str:
    return f"person:{addr}"


def map_messages(rows: Iterable[dict]) -> Iterator[Canonical]:
    """Map email rows to canonical records (entities, aggregated edges, documents).

    Edges between the same (sender, recipient) collapse to one ``EMAILED`` edge
    carrying ``count`` and ``first_seen``/``last_seen`` (ISO date strings).
    """
    people: dict[str, Entity] = {}
    edges: dict[tuple[str, str], dict[str, str]] = {}
    documents: list[Document] = []

    def _ensure(addr: str) -> str | None:
        norm = _norm(addr)
        if not norm:
            return None
        pid = _person_id(norm)
        people.setdefault(pid, Entity(id=pid, type="person", name=norm))
        return pid

    for row in rows:
        sender = _ensure(row.get("from", ""))
        recipients = [
            pid for a in (list(row.get("to") or []) + list(row.get("cc") or []))
            if (pid := _ensure(a))
        ]
        date = str(row.get("date") or "")
        if sender:
            for dst in recipients:
                edge = edges.setdefault(
                    (sender, dst), {"count": "0", "first_seen": date, "last_seen": date}
                )
                edge["count"] = str(int(edge["count"]) + 1)
                if date and date < edge["first_seen"]:
                    edge["first_seen"] = date
                if date and date > edge["last_seen"]:
                    edge["last_seen"] = date
        documents.append(Document(
            id=f"email:{row.get('message_id', '')}",
            text=str(row.get("body") or ""),
            source_entity_ids=tuple(p for p in [sender, *recipients] if p),
            metadata={"subject": str(row.get("subject") or ""), "date": date,
                      "from": _norm(row.get("from", "")), "file_name": str(row.get("file_name") or "")},
            modality="email_body",
        ))

    yield from people.values()
    for (src, dst), attrs in edges.items():
        yield Relationship(src=src, dst=dst, type="EMAILED", attributes=attrs)
    yield from documents
```

- [ ] **Step 5: run** `uv run python -m pytest tests/unit/test_enron_mapping.py -q` → PASS (4). `make lint` clean.

- [ ] **Step 6: Commit** `feat(datasets): Enron message→canonical mapping + data extra`

---

### Task 2: EnronAdapter — streaming load from Hugging Face

**Files:**
- Modify: `src/ariadne/datasets/enron.py` (add the adapter class + register), `src/ariadne/cli.py` (import enron so it registers — like synthetic)
- Test: `tests/unit/test_enron_adapter.py` (hermetic — monkeypatch the row source), `tests/integration/test_enron_load.py` (gated; needs `--extra data` + network)

- [ ] **Step 1: Hermetic unit test** (`tests/unit/test_enron_adapter.py`) — tests metadata + that `load()` routes its rows through `map_messages`, WITHOUT touching HF (inject rows via the seam):

```python
from __future__ import annotations

from ariadne.datasets.base import get_adapter
from ariadne.datasets.canonical import Entity
from ariadne.datasets.enron import EnronAdapter
import ariadne.datasets.enron  # noqa: F401  (registers it)


def test_adapter_metadata() -> None:
    a = EnronAdapter()
    assert a.name == "enron" and a.entity_type == "person" and a.access == "public"


def test_registered_in_the_registry() -> None:
    assert get_adapter("enron").name == "enron"


def test_load_maps_injected_rows(monkeypatch) -> None:
    rows = [{"message_id": "m", "from": "a@enron.com", "to": ["b@enron.com"],
             "cc": [], "subject": "s", "date": "2001-01-01", "body": "x",
             "file_name": "kaminski-v/1."}]
    a = EnronAdapter()
    monkeypatch.setattr(a, "_rows", lambda: iter(rows))
    names = {r.name for r in a.load() if isinstance(r, Entity)}
    assert {"a@enron.com", "b@enron.com"} <= names
```

- [ ] **Step 2: run** → FAIL.

- [ ] **Step 3: Implement** — append to `src/ariadne/datasets/enron.py`:

```python
from ariadne.datasets.base import register
from ariadne.evaluation.needle import NeedleFixture

_DATASET = "corbt/enron-emails"
_DEFAULT_MAILBOX = "kaminski-v"
_DEFAULT_LIMIT = 3000


class EnronAdapter:
    """Streams `corbt/enron-emails`, bounded to one mailbox, to canonical records."""

    name = "enron"
    entity_type = "person"
    access = "public"

    def __init__(self, mailbox: str = _DEFAULT_MAILBOX, limit: int = _DEFAULT_LIMIT) -> None:
        self.mailbox = mailbox
        self.limit = limit

    def _rows(self):
        # Lazy import: `datasets` is the optional `data` extra. Streaming avoids
        # downloading all ~517K rows; we filter to the target mailbox and cap.
        from datasets import load_dataset

        prefix = f"{self.mailbox}/"
        stream = load_dataset(_DATASET, split="train", streaming=True)
        taken = 0
        for row in stream:
            if not str(row.get("file_name") or "").startswith(prefix):
                continue
            yield row
            taken += 1
            if taken >= self.limit:
                break

    def load(self):
        return map_messages(self._rows())

    def eval_fixtures(self) -> list[NeedleFixture]:
        return [KAMINSKI_AOL_FIXTURE]


register(EnronAdapter())
```

(`KAMINSKI_AOL_FIXTURE` is defined in Task 3; to keep this task green before Task 3, temporarily `return []` and change it to `return [KAMINSKI_AOL_FIXTURE]` in Task 3. State this in the commit.)

In `src/ariadne/cli.py`, add next to the synthetic registration import:
```python
import ariadne.datasets.enron  # noqa: F401  (registers the enron adapter)
```

- [ ] **Step 4: run** unit → PASS (3). Confirm `enron` now appears in `ariadne workup --help`/`index --help` choices (it's in `sorted(DATASETS)`).

- [ ] **Step 5: Gated integration test** (`tests/integration/test_enron_load.py`):

```python
"""Live Enron load from Hugging Face (gated; needs `uv sync --extra data` + network)."""

from __future__ import annotations

import pytest

datasets = pytest.importorskip("datasets")  # skips unless the `data` extra is installed

from ariadne.datasets.canonical import Document, Entity, Relationship
from ariadne.datasets.enron import EnronAdapter

pytestmark = pytest.mark.integration


def test_streams_kaminski_mailbox_into_canonical_records() -> None:
    recs = list(EnronAdapter(mailbox="kaminski-v", limit=200).load())
    assert any(isinstance(r, Entity) and "kaminski" in r.name for r in recs)
    assert any(isinstance(r, Relationship) and r.type == "EMAILED" for r in recs)
    assert any(isinstance(r, Document) and r.modality == "email_body" for r in recs)
```

- [ ] **Step 6: run integration** (after `uv sync --extra data`): `uv run python -m pytest tests/integration/test_enron_load.py -q -m integration` → 1 passed (downloads a small stream slice; allow a minute). If `datasets` isn't installed it SKIPS — that's acceptable, but try to install + run it since this proves the real load.

- [ ] **Step 7: full suite + lint + commit.** `feat(datasets): EnronAdapter streaming load (kaminski-v mailbox, bounded)`

---

### Task 3: Enron eval fixture — the Kaminski cross-account needle

**Files:**
- Modify: `src/ariadne/datasets/enron.py` (define `KAMINSKI_AOL_FIXTURE`, wire `eval_fixtures`), `src/ariadne/evaluation/needle.py` (add to `FIXTURES`)
- Test: `tests/unit/test_enron_fixture.py`

- [ ] **Step 1: Failing test** (`tests/unit/test_enron_fixture.py`):

```python
from __future__ import annotations

from ariadne.datasets.enron import KAMINSKI_AOL_FIXTURE, map_messages
from ariadne.evaluation.needle import FIXTURES, score_workup

_ROWS = [
    {"message_id": f"m{i}", "from": "vince.kaminski@enron.com", "to": ["vkaminski@aol.com"],
     "cc": [], "subject": "fwd", "date": f"2001-05-1{i}", "body": "x", "file_name": "kaminski-v/s."}
    for i in range(3)
]


def test_fixture_is_registered() -> None:
    assert "kaminski-aol" in FIXTURES


def test_cross_account_tie_scores_grounded() -> None:
    # A note surfacing the AOL tie + a ledger that queried the EMAILED edge to it.
    note = "Kaminski forwards work mail to a personal account, vkaminski@aol.com."
    ledger = [{"id": "g1", "tool": "mcp__neo4j__read_neo4j_cypher",
               "tool_input": {"query": "MATCH (:Person {name:'vince.kaminski@enron.com'})"
                                       "-[:EMAILED]->(p) RETURN p.name"},
               "response_excerpt": "vkaminski@aol.com"}]
    report = score_workup(note, ledger, KAMINSKI_AOL_FIXTURE)
    assert report.grounded is True
```

- [ ] **Step 2: run** → FAIL.

- [ ] **Step 3: Implement.** In `enron.py`, define the fixture (place it above `EnronAdapter`, and change `eval_fixtures` to `return [KAMINSKI_AOL_FIXTURE]`):

```python
# The non-obvious cross-account tie: Kaminski forwards work mail to a personal
# AOL address — the same person under a second identity, surfaced only by the
# communication pattern. Real-data analog of the synthetic Halberd↔Wren needle.
KAMINSKI_AOL_FIXTURE = NeedleFixture(
    entity="vince.kaminski@enron.com",
    answer_markers=("vkaminski@aol.com",),
    traversal_markers=("EMAILED",),  # the ledger walked an EMAILED edge to surface it
    min_hops=1,
    supporting_facts=(
        SupportingFact(note_markers=("vkaminski@aol.com",), ledger_markers=("EMAILED",)),
    ),
)
```
Add the imports `from ariadne.evaluation.needle import NeedleFixture, SupportingFact`. In `src/ariadne/evaluation/needle.py`, register it in `FIXTURES`:
```python
# at the bottom, import-free: add to the FIXTURES dict
```
Because `needle.py` must not import `enron` (cycle), instead register from `enron.py` after the fixture is defined:
```python
from ariadne.evaluation.needle import FIXTURES
FIXTURES["kaminski-aol"] = KAMINSKI_AOL_FIXTURE
```
(Mutating the shared `FIXTURES` dict at enron-import time mirrors the adapter `register()` idiom and avoids a needle→enron import cycle. Ensure `import ariadne.datasets.enron` runs before the CLI reads `sorted(FIXTURES)` — it already does, via the cli.py registration import.)

- [ ] **Step 4: run** unit → PASS (2). Full suite → no regression. `make lint` clean.

- [ ] **Step 5: Commit** `feat(eval): Kaminski cross-account needle fixture (kaminski-aol)`

---

### Task 4: Docs — B2 notes

**Files:** Modify `IMPL.md`, `ROADMAP.md`, `docs/architecture/index.md`

- [ ] **Step 1:** `IMPL.md` — "Phase B2 shipped" entry: EnronAdapter (`corbt/enron-emails`, kaminski-v mailbox, streaming, `data` extra), `ariadne index --dataset enron`, the `kaminski-aol` cross-account needle. Reference this plan.
- [ ] **Step 2:** `ROADMAP.md` — mark B2 done; B3 (semantic pgvector leg + RRF → completes ADR-0007) is next.
- [ ] **Step 3:** `docs/architecture/index.md` — one tight sentence in the Datasets section: a second adapter (Enron email corpus) plugs in via the same canonical seam, proving generalization beyond the synthetic graph.
- [ ] **Step 4:** `uv run --with zensical zensical build` → "No issues found".
- [ ] **Step 5: Commit** `docs(datasets): Phase B2 (Enron adapter) notes`

---

## Phase B2 done (all true)

1. `map_messages` deterministically maps email rows to canonical Entity(person)/EMAILED(aggregated)/Document records (hermetic tests).
2. `EnronAdapter` streams `corbt/enron-emails` bounded to the `kaminski-v` mailbox; live load proven (gated, with `--extra data`).
3. `enron` is registered; `ariadne index --dataset enron` and `ariadne workup … --dataset enron` resolve it.
4. The `kaminski-aol` needle scores the cross-account tie; in `FIXTURES` and `EnronAdapter.eval_fixtures`.
5. `make lint` + full unit/smoke suite green; ADR/docs updated.

## Next

- **B3 — semantic leg:** pgvector column on `documents` + an in-process embed tool (EmbeddingGemma-300M; BGE-M3 fallback) + RRF fusion with the full-text leg → completes ADR-0007's hybrid.
- **Live demo smoke (manual):** `uv sync --extra data`, Colima up, `ariadne index --dataset enron`, then `ariadne workup vince.kaminski@enron.com --dataset enron --sql` and `ariadne eval <dir> --fixture kaminski-aol`.
