# Phase B1 — Live Indexing + Full-Text Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make the canonical pipeline *write to live stores* and retrieve unstructured text by full-text search — the lexical leg of the hybrid design, proven on the SyntheticAdapter's existing canonical output (no new data, no embeddings).

**Architecture:** A pure transform already exists (`index_graph`). B1 adds (a) a live graph loader that executes idempotent `MERGE` against Neo4j behind id-uniqueness constraints, (b) a Postgres document store with a generated `tsvector` column + GIN index and `websearch_to_tsquery` full-text search, and (c) an `ariadne index --dataset <name>` command. The agent retrieves text via the existing `postgres-mcp` `execute_sql` tool (no new connector). Vector/semantic leg + Enron adapter are later sub-phases.

**Tech Stack:** Python 3.14, `uv`, `ruff`, `pytest`; `neo4j` driver, `psycopg`, `testcontainers` (already deps). ENV: run tests as `uv run python -m pytest …` (NOT `uv run pytest`). Integration tests need Colima up (`colima start`).

> **Grounding (June 2026, verified):** generated `tsvector` column + GIN index + `websearch_to_tsquery` is the PG18 best-practice dependency-free FTS; Neo4j idempotent ingest = `MERGE` + uniqueness constraint on the merge key; agentic retrieval directly over SQL via `execute_sql` is a recognized pattern. → ADR-0007.

> **Commits:** AJ batches/pushes; commit per task with plain messages (NO Co-Authored-By / "Generated with" / 🤖 lines). Gate before each commit: `make lint && uv run python -m pytest tests/unit tests/test_smoke.py -q`.

---

### Task 1: ADR-0007 — Hybrid retrieval (full-text first, in-Postgres)

**Files:**
- Create: `docs/architecture/decisions/0007-hybrid-retrieval-fulltext-first.md`
- Modify: `docs/architecture/decisions/index.md` (add row), `zensical.toml` (nav)

- [ ] **Step 1: Write the ADR** (MADR format — read `0004`/`0006` for the template). Content:
  - **Status:** Accepted (2026-06-03).
  - **Context:** the unstructured/Document leg of the canonical pipeline needs retrieval; the spec calls for hybrid (lexical + semantic) but sequencing matters for PII/air-gap and dependency weight.
  - **Decision drivers:** exact-identifier lookup dominates email entity search; PII content should not require an embedding round-trip; keep dependencies lean; stay in the one access-controlled Postgres store.
  - **Considered options:** (A, chosen) full-text first via built-in `tsvector`/`websearch_to_tsquery` + GIN, semantic pgvector leg added later, fused by RRF — pro: zero new dep, no embedding step (PII-safe), exact-term precision; con: `ts_rank` lacks BM25 IDF. (B) BM25 extension now (`pg_textsearch` / ParadeDB) — better ranking, but a new extension + earlier complexity. (C) dedicated vector DB — rejected per ADR-0004 (consolidation).
  - **Decision:** A. Full-text via generated `tsvector` column + GIN + `websearch_to_tsquery`, queried through the existing `postgres-mcp` `execute_sql`. Upgrade paths noted: `pg_textsearch` (2026 C-native BM25, faster than ParadeDB, not Neon-deprecated) for ranking; pgvector + a small local embed model (EmbeddingGemma-300M; BGE-M3 fallback) for the semantic leg, fused by RRF.
  - **Consequences:** B1 ships lexical retrieval with no embedding dependency; semantic leg is an isolated follow-on; all retrieval stays in Postgres.
  - **Sources:** link https://www.postgresql.org/docs/current/textsearch-tables.html , https://www.tigerdata.com/blog/pg-textsearch-bm25-full-text-search-postgres , https://www.paradedb.com/blog/hybrid-search-in-postgresql-the-missing-manual

- [ ] **Step 2: Add the index row** to `docs/architecture/decisions/index.md` after the 0006 row:
```markdown
| [0007](0007-hybrid-retrieval-fulltext-first.md) | Hybrid retrieval, full-text first (in-Postgres) | Accepted |
```

- [ ] **Step 3: Add nav** in `zensical.toml` Decisions list after the 0006 line:
```toml
          { "0007 · Hybrid retrieval (full-text first)" = "architecture/decisions/0007-hybrid-retrieval-fulltext-first.md" },
```

- [ ] **Step 4: Verify** `uv run --with zensical zensical build` → "No issues found".

- [ ] **Step 5: Commit** `docs(adr): 0007 hybrid retrieval — full-text first, in-Postgres`

---

### Task 2: Postgres document store (schema + upsert + full-text search)

**Files:**
- Create: `src/ariadne/unstructured/__init__.py` (empty), `src/ariadne/unstructured/document_store.py`
- Test: `tests/unit/test_document_store_sql.py` (hermetic), `tests/integration/test_document_store_fts.py` (gated)

- [ ] **Step 1: Write the hermetic unit test** (`tests/unit/test_document_store_sql.py`) — verifies the SQL builders are well-formed without a DB:

```python
from __future__ import annotations

from ariadne.datasets.canonical import Attribute, Document
from ariadne.unstructured.document_store import (
    SCHEMA_DDL,
    document_rows,
    attribute_rows,
    full_text_sql,
)


def test_schema_uses_generated_tsvector_and_gin() -> None:
    ddl = "\n".join(SCHEMA_DDL)
    assert "GENERATED ALWAYS AS" in ddl and "to_tsvector" in ddl
    assert "USING gin" in ddl.lower()


def test_document_rows_map_canonical_fields() -> None:
    rows = document_rows([Document(id="email:1", text="hello world",
                                   source_entity_ids=("person:X",),
                                   metadata={"subject": "hi"}, modality="email_body")])
    assert rows[0]["id"] == "email:1"
    assert rows[0]["text"] == "hello world"
    assert rows[0]["modality"] == "email_body"


def test_attribute_rows_map_canonical_fields() -> None:
    rows = attribute_rows([Attribute(entity_id="person:X", key="role", value="Lead")])
    assert rows[0] == {"entity_id": "person:X", "key": "role", "value": "Lead"}


def test_full_text_sql_uses_websearch_tsquery() -> None:
    sql = full_text_sql()
    assert "websearch_to_tsquery" in sql and "content_tsv" in sql and "%(q)s" in sql
```

- [ ] **Step 2: Run** `uv run python -m pytest tests/unit/test_document_store_sql.py -q` → FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement** `src/ariadne/unstructured/document_store.py`:

```python
"""Postgres document store — the full-text (lexical) retrieval leg.

A generated ``tsvector`` column + GIN index gives dependency-free full-text
search via ``websearch_to_tsquery``; the agent queries it through the existing
``postgres-mcp`` ``execute_sql`` tool. The semantic (pgvector) leg is a later
sub-phase. See ADR-0007.
"""

from __future__ import annotations

from collections.abc import Iterable

from ariadne.datasets.canonical import Attribute, Canonical, Document

# Idempotent DDL (run once per store). The generated tsvector column means the
# text is preprocessed at write time; a GIN index makes @@ lookups fast.
SCHEMA_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS documents (
        id        TEXT PRIMARY KEY,
        text      TEXT NOT NULL,
        modality  TEXT NOT NULL DEFAULT 'text',
        metadata  JSONB NOT NULL DEFAULT '{}'::jsonb,
        sources   TEXT[] NOT NULL DEFAULT '{}',
        content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
    )
    """,
    "CREATE INDEX IF NOT EXISTS documents_tsv_gin ON documents USING gin (content_tsv)",
    """
    CREATE TABLE IF NOT EXISTS entity_attributes (
        entity_id TEXT NOT NULL,
        key       TEXT NOT NULL,
        value     TEXT NOT NULL,
        PRIMARY KEY (entity_id, key)
    )
    """,
)

_UPSERT_DOC = (
    "INSERT INTO documents (id, text, modality, metadata, sources) "
    "VALUES (%(id)s, %(text)s, %(modality)s, %(metadata)s, %(sources)s) "
    "ON CONFLICT (id) DO UPDATE SET text = EXCLUDED.text, modality = EXCLUDED.modality, "
    "metadata = EXCLUDED.metadata, sources = EXCLUDED.sources"
)
_UPSERT_ATTR = (
    "INSERT INTO entity_attributes (entity_id, key, value) "
    "VALUES (%(entity_id)s, %(key)s, %(value)s) "
    "ON CONFLICT (entity_id, key) DO UPDATE SET value = EXCLUDED.value"
)


def document_rows(records: Iterable[Canonical]) -> list[dict]:
    import json

    rows: list[dict] = []
    for rec in records:
        if isinstance(rec, Document):
            rows.append({
                "id": rec.id, "text": rec.text, "modality": rec.modality,
                "metadata": json.dumps(rec.metadata), "sources": list(rec.source_entity_ids),
            })
    return rows


def attribute_rows(records: Iterable[Canonical]) -> list[dict]:
    return [
        {"entity_id": r.entity_id, "key": r.key, "value": r.value}
        for r in records if isinstance(r, Attribute)
    ]


def full_text_sql() -> str:
    """Parameterised full-text query (``%(q)s`` = natural-language search string)."""
    return (
        "SELECT id, text, modality, metadata, "
        "ts_rank(content_tsv, websearch_to_tsquery('english', %(q)s)) AS rank "
        "FROM documents "
        "WHERE content_tsv @@ websearch_to_tsquery('english', %(q)s) "
        "ORDER BY rank DESC LIMIT %(limit)s"
    )


def ensure_schema(conn) -> None:
    for stmt in SCHEMA_DDL:
        conn.execute(stmt.encode())


def upsert_documents(conn, records: Iterable[Canonical]) -> int:
    rows = document_rows(records)
    for row in rows:
        conn.execute(_UPSERT_DOC.encode(), row)
    return len(rows)


def upsert_attributes(conn, records: Iterable[Canonical]) -> int:
    rows = attribute_rows(records)
    for row in rows:
        conn.execute(_UPSERT_ATTR.encode(), row)
    return len(rows)
```

- [ ] **Step 4: Run** `uv run python -m pytest tests/unit/test_document_store_sql.py -q` → PASS (4).

- [ ] **Step 5: Write the gated integration test** (`tests/integration/test_document_store_fts.py`) — mirrors `test_postgres_seed.py`'s container style:

```python
"""Full-text retrieval over the document store (gated; needs Docker/Colima)."""

from __future__ import annotations

import pytest

pytest.importorskip("testcontainers")
pytest.importorskip("psycopg")

import psycopg
from testcontainers.postgres import PostgresContainer

from ariadne.datasets.canonical import Document
from ariadne.unstructured.document_store import ensure_schema, full_text_sql, upsert_documents

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def pg_conn():
    with PostgresContainer("postgres:17") as pg:
        info = (f"host={pg.get_container_host_ip()} port={pg.get_exposed_port(5432)} "
                f"user={pg.username} password={pg.password} dbname={pg.dbname}")
        with psycopg.connect(info, autocommit=True) as conn:
            ensure_schema(conn)
            yield conn


def test_full_text_finds_the_matching_document(pg_conn) -> None:
    upsert_documents(pg_conn, [
        Document(id="e1", text="The shipment leaves Compound-Alpha at dawn."),
        Document(id="e2", text="Budget review for the quarter, no logistics content."),
    ])
    rows = pg_conn.execute(full_text_sql().encode(),
                           {"q": "Compound-Alpha shipment", "limit": 5}).fetchall()
    assert rows and rows[0][0] == "e1"


def test_upsert_is_idempotent(pg_conn) -> None:
    doc = Document(id="dup", text="repeated insert")
    upsert_documents(pg_conn, [doc])
    upsert_documents(pg_conn, [doc])
    n = pg_conn.execute(b"SELECT count(*) FROM documents WHERE id = 'dup'").fetchone()[0]
    assert n == 1
```

- [ ] **Step 6: Run integration** (Colima must be up): `uv run python -m pytest tests/integration/test_document_store_fts.py -q -m integration` → 2 passed. If Docker is down, note SKIPPED and proceed (the hermetic unit tests are the gate).

- [ ] **Step 7: `make lint`; Commit** `feat(unstructured): Postgres document store with tsvector full-text search`

---

### Task 3: Live store loaders (graph + documents)

**Files:**
- Create: `src/ariadne/datasets/load.py`
- Test: `tests/unit/test_load_graph_cypher.py` (hermetic), `tests/integration/test_live_indexing.py` (gated)

- [ ] **Step 1: Hermetic unit test** (`tests/unit/test_load_graph_cypher.py`) — verifies constraint derivation without a DB, using a fake session that records run statements:

```python
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
```

- [ ] **Step 2: Run** → FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement** `src/ariadne/datasets/load.py`:

```python
"""Execute canonical records into live stores.

Pure statement-building (``graph_statements``) stays unit-testable; the
``load_*`` functions run them against a driver/connection. Graph ingest is
idempotent via per-label id-uniqueness constraints + the MERGE statements from
``index_graph`` (ADR-0007 / best-practice MERGE-with-constraint).
"""

from __future__ import annotations

from collections.abc import Iterable

from ariadne.datasets.canonical import Canonical, Entity
from ariadne.datasets.indexer import _label, index_graph
from ariadne.unstructured.document_store import (
    ensure_schema,
    upsert_attributes,
    upsert_documents,
)


def graph_statements(records: list[Canonical]) -> list[str]:
    """Constraints (one per distinct entity label) first, then MERGE statements."""
    labels = sorted({_label(r.type) for r in records if isinstance(r, Entity)})
    constraints = [
        f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{lbl}) REQUIRE n.id IS UNIQUE"
        for lbl in labels
    ]
    return constraints + index_graph(records)


def load_graph(records: list[Canonical], driver) -> int:
    stmts = graph_statements(records)
    with driver.session() as session:
        for stmt in stmts:
            session.run(stmt)
    return len(stmts)


def load_documents(records: Iterable[Canonical], conn) -> tuple[int, int]:
    records = list(records)
    ensure_schema(conn)
    return upsert_documents(conn, records), upsert_attributes(conn, records)
```

Note: importing the private `_label` from `indexer` is the deliberate single source of truth for the type→label mapping. If the reviewer prefers, promote `_label` to a public `label(type)` in `indexer.py` and update the one call site in `synthetic`/tests — controller decides.

- [ ] **Step 4: Run** `uv run python -m pytest tests/unit/test_load_graph_cypher.py -q` → PASS (2).

- [ ] **Step 5: Gated integration test** (`tests/integration/test_live_indexing.py`) — uses the existing `neo4j_conn` session fixture from `tests/integration/conftest.py` (note: that fixture SEEDS the graph from seed.cypher; for a clean load test, wipe first):

```python
"""Live indexing: SyntheticAdapter canonical -> Neo4j; query the planted bridge."""

from __future__ import annotations

import pytest

pytest.importorskip("testcontainers")

from neo4j import GraphDatabase

from ariadne.datasets.load import load_graph
from ariadne.datasets.synthetic import SyntheticAdapter

pytestmark = pytest.mark.integration


def test_load_graph_reproduces_the_colocation_bridge(neo4j_conn) -> None:
    driver = GraphDatabase.driver(
        neo4j_conn["uri"], auth=(neo4j_conn["username"], neo4j_conn["password"])
    )
    with driver.session() as s:
        s.run("MATCH (n) DETACH DELETE n")  # clean slate (fixture pre-seeded)
    load_graph(list(SyntheticAdapter().load()), driver)
    with driver.session() as s:
        rec = s.run(
            "MATCH (h:Person {id:'person:Halberd'})-[:MEMBER_OF]->(:Unit)"
            "-[:CO_LOCATED]->(site:Site)<-[:CO_LOCATED]-(:Unit)<-[:MEMBER_OF]-"
            "(w:Person {id:'person:Wren'}) RETURN site.name AS site"
        ).single()
    driver.close()
    assert rec is not None and rec["site"] == "Compound-Alpha"
```

- [ ] **Step 6: Run integration** (Colima up): `uv run python -m pytest tests/integration/test_live_indexing.py -q -m integration` → 1 passed (or SKIPPED if Docker down — note it).

- [ ] **Step 7: `make lint`; Commit** `feat(datasets): live graph + document loaders (idempotent, constraint-backed)`

---

### Task 4: `ariadne index --dataset <name>` command

**Files:**
- Modify: `src/ariadne/cli.py`
- Test: `tests/unit/test_cli_index.py`

- [ ] **Step 1: Failing test** (`tests/unit/test_cli_index.py`):

```python
from __future__ import annotations

import pytest

from ariadne.cli import parse_args


def test_index_defaults_to_synthetic() -> None:
    args = parse_args(["index"])
    assert args.command == "index" and args.dataset == "synthetic"


def test_index_rejects_unknown_dataset() -> None:
    with pytest.raises(SystemExit):
        parse_args(["index", "--dataset", "nope"])
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement** in `src/ariadne/cli.py`: add an `index` subparser and a handler. In `parse_args`, after the `eval` subparser:
```python
    ix = sub.add_parser("index", help="Load a dataset's records into the live stores")
    ix.add_argument("--dataset", choices=sorted(DATASETS), default="synthetic",
                    help="Dataset to index (default: synthetic).")
```
Add a handler that loads graph + documents (reads NEO4J_*/DATABASE_URI from env, same defaults as the connectors):
```python
def _run_index(dataset: str, env: dict[str, str]) -> int:
    from neo4j import GraphDatabase
    import psycopg
    from ariadne.datasets.base import get_adapter
    from ariadne.datasets.load import load_documents, load_graph

    records = list(get_adapter(dataset).load())
    driver = GraphDatabase.driver(
        env.get("NEO4J_URI", "bolt://localhost:7687"),
        auth=(env.get("NEO4J_USERNAME", "neo4j"), env.get("NEO4J_PASSWORD", "password")),
    )
    n_graph = load_graph(records, driver)
    driver.close()
    n_docs = (0, 0)
    with psycopg.connect(
        env.get("DATABASE_URI", "postgresql://ariadne:ariadne@localhost:5432/intel"),
        autocommit=True,
    ) as conn:
        n_docs = load_documents(records, conn)
    print(f"Indexed {dataset}: {n_graph} graph statements, "
          f"{n_docs[0]} documents, {n_docs[1]} attributes.")
    return 0
```
Wire in `main` (after the `eval` branch, before the key check):
```python
    if args.command == "index":
        return _run_index(args.dataset, dict(os.environ))
```

- [ ] **Step 4: Run** `uv run python -m pytest tests/unit/test_cli_index.py -q` → PASS (2). Then full suite `uv run python -m pytest tests/unit tests/test_smoke.py -q` → no regression.

- [ ] **Step 5: `make lint`; Commit** `feat(cli): ariadne index --dataset loads canonical records into live stores`

---

### Task 5: Docs — Phase B1 notes + entity-workup full-text guidance

**Files:**
- Modify: `IMPL.md`, `ROADMAP.md`, `docs/architecture/index.md`, `.claude/skills/entity-workup/SKILL.md`

- [ ] **Step 1:** `IMPL.md` — add a "Phase B1 shipped" entry (live indexing + Postgres full-text; `ariadne index`; ADR-0007). `ROADMAP.md` — mark B1 done under the multi-dataset expansion; B2 (Enron adapter) + B3 (semantic pgvector leg) next.
- [ ] **Step 2:** `docs/architecture/index.md` — one tight sentence in the Datasets section that text retrieval is full-text-first via Postgres `tsvector` (ADR-0007).
- [ ] **Step 3:** `.claude/skills/entity-workup/SKILL.md` — add a brief instruction: for free-text/email evidence, the agent may full-text search documents via `execute_sql` using `content_tsv @@ websearch_to_tsquery('english', '<terms>')`, ordering by `ts_rank`, and cite results like any other evidence. Keep it terse.
- [ ] **Step 4:** `uv run --with zensical zensical build` → "No issues found".
- [ ] **Step 5: Commit** `docs(datasets): Phase B1 notes + full-text retrieval guidance in entity-workup`

---

## Phase B1 done (all true)

1. `ensure_schema` creates a `documents` table with a generated `tsvector` column + GIN index; `full_text_sql` finds the matching doc via `websearch_to_tsquery` (integration-proven).
2. `load_graph` idempotently writes the SyntheticAdapter's canonical records to Neo4j behind per-label id-uniqueness constraints; the planted Halberd↔Compound-Alpha↔Wren bridge is queryable (integration-proven).
3. `ariadne index --dataset synthetic` loads graph + documents into the live stores.
4. Upserts are idempotent (re-running indexes once).
5. ADR-0007 written + in nav; `make lint` + full unit/smoke suite green; integration tests pass with Colima up (or skip cleanly without it).

## Next sub-phases

- **B2 — Enron adapter:** `corbt/enron-emails` → canonical (headers→Entity/Relationship, body→Document, meta→Attribute); fed through `ariadne index --dataset enron`; an Enron eval fixture. Fetch the dataset card for exact columns first.
- **B3 — Semantic leg:** pgvector column + in-process embed tool (EmbeddingGemma-300M; BGE-M3 fallback) + RRF fusion with the full-text leg.
