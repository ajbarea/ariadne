# Phase B3.1 — Semantic Leg (pgvector + embeddings + RRF) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox (`- [ ]`) steps.

**Goal:** Build the semantic half of ADR-0007's hybrid retrieval — an injectable embedder, a pgvector column + HNSW index on the B1 `documents` table, and an RRF query that fuses the full-text and vector legs. The retrieval *data layer*; wiring it as a live agent tool is B3.2.

**Architecture:** An `Embedder` Protocol (declared `dim`, `embed(texts)`) — dependency-injected exactly like the HHEM `EntailmentVerifier`. A `FakeEmbedder` keeps the core hermetic; a real `SentenceTransformerEmbedder` (default `bge-small-en-v1.5`, 384-dim, ungated) lives behind an optional `embed` extra (lazy `importlib`). The B1 document store gains a nullable `embedding vector(N)` column + HNSW cosine index; `hybrid_search` embeds the query and fuses full-text + vector rankings with RRF in one SQL query.

**Tech Stack:** Python 3.14, `uv`, `ruff`, `pytest`; `sentence-transformers` behind the optional `embed` extra; pgvector via the `pgvector/pgvector:pg17` testcontainer image. ENV: pytest is `uv run python -m pytest …` (NOT `uv run pytest`). pgvector integration needs Colima up (≥4GiB).

> **Grounding (June 2026, verified):** HNSW `vector_cosine_ops` (m=16, ef_construction=64) is the pgvector default; `vector(N)` (N≤2000 for HNSW); RRF = `1/(k+rank)`, k=60, ~20 candidates/side, fuses full-text + vector without score normalization (62%→84%+ precision over pure vector). `bge-small-en-v1.5` is 384-dim, Apache-2.0, ungated (no license friction); EmbeddingGemma-300M is the gated 768-dim swap.

> **Commits:** plain messages, NO Co-Authored-By / "Generated with" / 🤖. Gate: `make lint && uv run python -m pytest tests/unit tests/test_smoke.py -q`.

---

### Task 1: Embedder protocol + fake + real (behind `embed` extra)

**Files:**
- Modify: `pyproject.toml` (`embed = ["sentence-transformers>=3"]`), `uv.lock`
- Create: `src/ariadne/unstructured/embed.py`
- Test: `tests/unit/test_embed.py` (hermetic), `tests/integration/test_embed_real.py` (gated)

- [ ] **Step 1: Add the extra.** In `pyproject.toml` `[project.optional-dependencies]`, add `embed = ["sentence-transformers>=3"]`. Run `uv lock`. Do NOT `uv sync --extra embed` for the hermetic tests.

- [ ] **Step 2: Failing hermetic test** (`tests/unit/test_embed.py`):

```python
from __future__ import annotations

from ariadne.unstructured.embed import Embedder, FakeEmbedder


def test_fake_embedder_is_deterministic_and_fixed_dim() -> None:
    e: Embedder = FakeEmbedder(dim=8)
    v1 = e.embed(["hello world"])
    v2 = e.embed(["hello world"])
    assert v1 == v2  # deterministic
    assert len(v1) == 1 and len(v1[0]) == 8  # one vector, dim 8
    assert e.dim == 8


def test_fake_embedder_differs_by_text() -> None:
    e = FakeEmbedder(dim=8)
    assert e.embed(["a"])[0] != e.embed(["b"])[0]
```

- [ ] **Step 3: run** → FAIL.

- [ ] **Step 4: Implement** `src/ariadne/unstructured/embed.py`:

```python
"""Text embedding for the semantic retrieval leg (ADR-0007).

The ``Embedder`` is dependency-injected (like the HHEM ``EntailmentVerifier``)
so the core/tests stay hermetic via ``FakeEmbedder``; the real
``SentenceTransformerEmbedder`` lives behind the optional ``embed`` extra and is
lazy-imported so the static checker stays stable without it. Default model is
the ungated ``bge-small-en-v1.5`` (384-dim, Apache-2.0); EmbeddingGemma-300m
(768-dim, gated) is a swap.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Protocol


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FakeEmbedder:
    """Deterministic hash-based embedder for hermetic tests (no model)."""

    def __init__(self, dim: int = 8) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            # repeat the digest to fill dim floats in [0,1)
            vals = [b / 255.0 for b in digest]
            out.append([vals[i % len(vals)] for i in range(self.dim)])
        return out


_DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
_DEFAULT_DIM = 384


class SentenceTransformerEmbedder:
    """Real embedder via sentence-transformers (optional ``embed`` extra)."""

    def __init__(self, model: str = _DEFAULT_MODEL, dim: int = _DEFAULT_DIM) -> None:
        self.model_name = model
        self.dim = dim
        self._model = None

    def _load(self):
        if self._model is None:
            import importlib

            st = importlib.import_module("sentence_transformers")
            self._model = st.SentenceTransformer(self.model_name)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        vecs = self._load().encode(texts, normalize_embeddings=True)
        return [list(map(float, v)) for v in vecs]
```

- [ ] **Step 5: run** `uv run python -m pytest tests/unit/test_embed.py -q` → PASS (2). `make lint` clean.

- [ ] **Step 6: Gated real-embed test** (`tests/integration/test_embed_real.py`):

```python
"""Real sentence-transformers embedding (gated; needs `uv sync --extra embed` + model download)."""

from __future__ import annotations

import pytest

pytest.importorskip("sentence_transformers")

from ariadne.unstructured.embed import SentenceTransformerEmbedder

pytestmark = pytest.mark.integration


def test_real_embedder_returns_unit_dim_vectors() -> None:
    e = SentenceTransformerEmbedder()
    vecs = e.embed(["the shipment leaves at dawn", "quarterly budget review"])
    assert len(vecs) == 2 and len(vecs[0]) == e.dim == 384
    assert vecs[0] != vecs[1]
```

- [ ] **Step 7: run integration** (`uv sync --extra embed`, then `uv run python -m pytest tests/integration/test_embed_real.py -q -m integration` — downloads ~130MB bge-small; allow a couple minutes). Get it green; if network-blocked, report blocked-with-error (don't fake).

- [ ] **Step 8: full suite + lint + commit.** `feat(unstructured): injectable Embedder (fake + sentence-transformers, embed extra)`

---

### Task 2: pgvector column + HNSW index on documents

**Files:**
- Modify: `src/ariadne/unstructured/document_store.py`
- Test: `tests/unit/test_document_store_vector_sql.py` (hermetic), `tests/integration/test_document_store_vector.py` (gated, pgvector image)

- [ ] **Step 1: Hermetic SQL-builder test** (`tests/unit/test_document_store_vector_sql.py`):

```python
from __future__ import annotations

from ariadne.unstructured.document_store import vector_ddl, store_embedding_sql


def test_vector_ddl_creates_extension_column_and_hnsw_index() -> None:
    ddl = "\n".join(vector_ddl(dim=384))
    assert "CREATE EXTENSION IF NOT EXISTS vector" in ddl
    assert "vector(384)" in ddl
    assert "USING hnsw" in ddl and "vector_cosine_ops" in ddl


def test_store_embedding_sql_is_parameterised_upsert() -> None:
    sql = store_embedding_sql()
    assert "UPDATE documents SET embedding" in sql
    assert "%(embedding)s" in sql and "%(id)s" in sql
```

- [ ] **Step 2: run** → FAIL.

- [ ] **Step 3: Implement** — append to `src/ariadne/unstructured/document_store.py`:

```python
def vector_ddl(dim: int) -> tuple[str, ...]:
    """DDL to add the pgvector column + HNSW cosine index (idempotent)."""
    return (
        "CREATE EXTENSION IF NOT EXISTS vector",
        f"ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding vector({dim})",
        "CREATE INDEX IF NOT EXISTS documents_embedding_hnsw "
        "ON documents USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)",
    )


def store_embedding_sql() -> str:
    """Parameterised: write one document's embedding (``%(embedding)s`` = '[...]' vector literal)."""
    return "UPDATE documents SET embedding = %(embedding)s::vector WHERE id = %(id)s"


def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def ensure_vector_schema(conn, dim: int) -> None:
    for stmt in vector_ddl(dim):
        conn.execute(stmt.encode())


def store_embeddings(conn, id_to_vec: dict[str, list[float]]) -> int:
    sql = store_embedding_sql().encode()
    for doc_id, vec in id_to_vec.items():
        conn.execute(sql, {"id": doc_id, "embedding": _vector_literal(vec)})
    return len(id_to_vec)
```

- [ ] **Step 4: run** unit → PASS (2). `make lint` clean.

- [ ] **Step 5: Gated integration** (`tests/integration/test_document_store_vector.py`) — uses the **pgvector image** (not plain postgres:17):

```python
"""pgvector column + nearest-neighbour query (gated; needs Docker/Colima)."""

from __future__ import annotations

import pytest

pytest.importorskip("testcontainers")
pytest.importorskip("psycopg")

import psycopg
from testcontainers.postgres import PostgresContainer

from ariadne.datasets.canonical import Document
from ariadne.unstructured.document_store import (
    _vector_literal, ensure_schema, ensure_vector_schema, store_embeddings, upsert_documents,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def pg_conn():
    with PostgresContainer("pgvector/pgvector:pg17") as pg:
        info = (f"host={pg.get_container_host_ip()} port={pg.get_exposed_port(5432)} "
                f"user={pg.username} password={pg.password} dbname={pg.dbname}")
        with psycopg.connect(info, autocommit=True) as conn:
            ensure_schema(conn)
            ensure_vector_schema(conn, dim=4)
            yield conn


def test_nearest_neighbour_returns_the_closest_vector(pg_conn) -> None:
    upsert_documents(pg_conn, [Document(id="a", text="alpha"), Document(id="b", text="beta")])
    store_embeddings(pg_conn, {"a": [1.0, 0.0, 0.0, 0.0], "b": [0.0, 1.0, 0.0, 0.0]})
    q = _vector_literal([0.9, 0.1, 0.0, 0.0])
    row = pg_conn.execute(
        b"SELECT id FROM documents WHERE embedding IS NOT NULL "
        b"ORDER BY embedding <=> %(q)s::vector LIMIT 1", {"q": q}
    ).fetchone()
    assert row[0] == "a"
```

- [ ] **Step 6: run integration** (Colima up): `uv run python -m pytest tests/integration/test_document_store_vector.py -q -m integration` → 1 passed (pulls the pgvector image first time). Get it green.

- [ ] **Step 7: full suite + lint + commit.** `feat(unstructured): pgvector column + HNSW cosine index on documents`

---

### Task 3: Hybrid RRF search (fuse full-text + vector)

**Files:**
- Modify: `src/ariadne/unstructured/document_store.py`
- Test: `tests/unit/test_hybrid_search_sql.py` (hermetic), `tests/integration/test_hybrid_search.py` (gated, pgvector image)

- [ ] **Step 1: Hermetic test** (`tests/unit/test_hybrid_search_sql.py`):

```python
from __future__ import annotations

from ariadne.unstructured.document_store import hybrid_search_sql


def test_hybrid_sql_fuses_fulltext_and_vector_with_rrf() -> None:
    sql = hybrid_search_sql()
    assert "websearch_to_tsquery" in sql            # full-text leg
    assert "<=>" in sql and "::vector" in sql        # vector leg
    assert "FULL OUTER JOIN" in sql                  # union of both legs
    assert "1.0 / (%(k)s +" in sql.replace(" ", " ")  # RRF term
    assert "%(q)s" in sql and "%(qvec)s" in sql and "%(limit)s" in sql
```

- [ ] **Step 2: run** → FAIL.

- [ ] **Step 3: Implement** — append to `document_store.py`:

```python
def hybrid_search_sql(candidates: int = 20) -> str:
    """RRF-fused full-text + vector search.

    Params: ``%(q)s`` natural-language query, ``%(qvec)s`` the query embedding as
    a '[...]' vector literal, ``%(k)s`` RRF smoothing (use 60), ``%(limit)s``.
    Each leg contributes ``1/(k+rank)``; ranks come from row_number() over each
    leg's ordering. (ADR-0007; RRF needs no score normalization.)
    """
    cand = int(candidates)
    return (
        "WITH fts AS ("
        "  SELECT id, row_number() OVER ("
        "    ORDER BY ts_rank(content_tsv, websearch_to_tsquery('english', %(q)s)) DESC) AS rank"
        "  FROM documents WHERE content_tsv @@ websearch_to_tsquery('english', %(q)s)"
        f"  LIMIT {cand}), "
        "vec AS ("
        "  SELECT id, row_number() OVER (ORDER BY embedding <=> %(qvec)s::vector) AS rank"
        "  FROM documents WHERE embedding IS NOT NULL"
        f"  ORDER BY embedding <=> %(qvec)s::vector LIMIT {cand}) "
        "SELECT COALESCE(fts.id, vec.id) AS id, "
        "  COALESCE(1.0 / (%(k)s + fts.rank), 0) + COALESCE(1.0 / (%(k)s + vec.rank), 0) AS rrf "
        "FROM fts FULL OUTER JOIN vec USING (id) "
        "ORDER BY rrf DESC LIMIT %(limit)s"
    )


def hybrid_search(conn, query: str, embedder, *, k: int = 60, limit: int = 10) -> list[str]:
    """Embed ``query`` and return RRF-fused document ids (full-text + vector)."""
    qvec = _vector_literal(embedder.embed([query])[0])
    rows = conn.execute(
        hybrid_search_sql().encode(),
        {"q": query, "qvec": qvec, "k": k, "limit": limit},
    ).fetchall()
    return [r[0] for r in rows]
```

- [ ] **Step 4: run** unit → PASS. `make lint` clean.

- [ ] **Step 5: Gated integration** (`tests/integration/test_hybrid_search.py`) — pgvector image + `FakeEmbedder`:

```python
"""Hybrid RRF search fuses full-text + vector (gated; pgvector image + fake embedder)."""

from __future__ import annotations

import pytest

pytest.importorskip("testcontainers")
pytest.importorskip("psycopg")

import psycopg
from testcontainers.postgres import PostgresContainer

from ariadne.datasets.canonical import Document
from ariadne.unstructured.document_store import (
    ensure_schema, ensure_vector_schema, hybrid_search, store_embeddings, upsert_documents,
)
from ariadne.unstructured.embed import FakeEmbedder

pytestmark = pytest.mark.integration


def test_hybrid_search_finds_a_doc_by_either_leg() -> None:
    emb = FakeEmbedder(dim=8)
    with PostgresContainer("pgvector/pgvector:pg17") as pg:
        info = (f"host={pg.get_container_host_ip()} port={pg.get_exposed_port(5432)} "
                f"user={pg.username} password={pg.password} dbname={pg.dbname}")
        with psycopg.connect(info, autocommit=True) as conn:
            ensure_schema(conn)
            ensure_vector_schema(conn, dim=emb.dim)
            docs = [Document(id="a", text="the shipment leaves Compound-Alpha at dawn"),
                    Document(id="b", text="quarterly budget review notes")]
            upsert_documents(conn, docs)
            store_embeddings(conn, {d.id: emb.embed([d.text])[0] for d in docs})
            # full-text leg should surface "a" for the shipment query
            ids = hybrid_search(conn, "Compound-Alpha shipment", emb, limit=5)
            assert "a" in ids and ids[0] == "a"
```

- [ ] **Step 6: run integration** (Colima up) → 1 passed.

- [ ] **Step 7: full suite + lint + commit.** `feat(unstructured): hybrid RRF search fusing full-text + pgvector`

---

### Task 4: Docs — B3.1 notes

**Files:** `IMPL.md`, `ROADMAP.md`, `docs/architecture/index.md`, and a one-line amendment to `docs/architecture/decisions/0007-hybrid-retrieval-fulltext-first.md`

- [ ] **Step 1:** ADR-0007 — add a one-line note that the default embedder is the **ungated `bge-small-en-v1.5` (384-dim)** with EmbeddingGemma-300m (gated, 768-dim) as the documented swap (the model is injectable via the `Embedder` protocol).
- [ ] **Step 2:** `IMPL.md` — "Phase B3.1 shipped": injectable `Embedder` (fake + sentence-transformers `embed` extra), pgvector column + HNSW cosine index, `hybrid_search` RRF fusion. Reference this plan.
- [ ] **Step 3:** `ROADMAP.md` — mark B3.1 (semantic leg, data layer) done; **B3.2** (wire `hybrid_search` as an in-process agent tool into `workup` + provenance + skill) is the remaining piece to fully realize ADR-0007 in the live loop.
- [ ] **Step 4:** `docs/architecture/index.md` — one sentence: unstructured retrieval is now hybrid (full-text + pgvector, RRF-fused), per ADR-0007.
- [ ] **Step 5:** `uv run --with zensical zensical build` → "No issues found". Commit `docs: Phase B3.1 (semantic leg) notes + ADR-0007 embedder default`.

---

## Phase B3.1 done (all true)

1. `Embedder` protocol with a hermetic `FakeEmbedder` and a real `SentenceTransformerEmbedder` (default ungated bge-small, behind the `embed` extra); real embed proven gated.
2. `documents` gains a `vector(N)` column + HNSW cosine index; nearest-neighbour query works (pgvector image, integration-proven).
3. `hybrid_search` embeds the query and returns RRF-fused full-text + vector ids (integration-proven with the fake embedder).
4. `make lint` + full unit/smoke green; gated integration green with Colima up.
5. ADR-0007 amended (ungated default); docs updated.

## Next — B3.2

Expose `hybrid_search` as an in-process agent tool (`mcp__ariadne__hybrid_search` or SDK tool), add its prefix to the provenance hook's `EVIDENCE_TOOL_PREFIXES`, and update the `entity-workup` skill so a `workup` semantically searches email bodies — completing ADR-0007's hybrid in the live loop. Then the live Kaminski demo exercises full-text + semantic + graph together.
