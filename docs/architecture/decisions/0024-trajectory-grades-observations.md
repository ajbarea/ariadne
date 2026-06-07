# 0024, Trajectory grades observations, not just actions

- **Status:** Accepted (2026-06-07)
- **Deciders:** Ariadne maintainers
- **Touches:** `evaluation/_text.py`, `evaluation/needle.py` (the planted-needle scorer)

## Context

The planted-needle `trajectory` score (and the per-edge supporting-fact F1)
answers the brief's "did the provenance *traverse* the path, or guess?" by
checking that the fixture's `traversal_markers` — the bridge **relationship
types** `MEMBER_OF` / `CO_LOCATED` — appear in the ledger. The scan
(`statement_text`) reads **only the tool *action*** — the Cypher/SQL query text.

A live Halberd two-store workup (2026-06-07) scored `trajectory=0.00`,
`grounded=False` — yet the agent **demonstrably walked the entire bridge**. It
just used **untyped, enumerate-everything** Cypher:

```cypher
MATCH (h:Person {name:'Halberd'})-[r]-(o) RETURN type(r) AS rel, ...   -- g7
MATCH (u:Unit {name:'Signals-Cell'})-[r]-(o) RETURN type(r) ...        -- g9
MATCH (s:Site {name:'Compound-Alpha'})-[r]-(o) RETURN type(r) ...      -- g11
```

The relationship types land in the **observations**, not the query strings:
g7 → `"rel":"MEMBER_OF"` (Halberd→Signals-Cell), g9 → `"rel":"CO_LOCATED"`
(Signals-Cell→Compound-Alpha), g11 → `"rel":"CO_LOCATED"`
(Compound-Alpha→Logistics-Cell). Action-only grading misses them and scores a
thorough, correct, fully-grounded traversal as a *guess*. Worse, the
untyped-enumeration style is arguably **better tradecraft** (it discovers every
edge rather than only the ones the agent assumed), so the metric penalises the
better behaviour. The score also flips with query phrasing run-to-run, which
makes it **unreliable** — unacceptable for the harness that certifies "what works."

## Decision drivers

- **2026 trajectory eval grades the (action, observation) pair.** `# research(2026-06):`
  the agent "selects a tool-use action … which yields a corresponding observation,"
  and trajectory-level assessment evaluates the retrieval *behaviour*, not just the
  call; **answer grounding is judged against what was *retrieved*** (the SoK on
  Agentic RAG arXiv:2603.07379; hop-aware AgenticRAGTracer arXiv:2602.19127, our
  existing citation). A retrieved edge is the *strongest* proof a hop was walked.
- **But a catalog/schema call is not traversal.** `CALL db.relationshipTypes()`
  (g3) returns the bare list of *all* rel types — including `MEMBER_OF`/`CO_LOCATED`
  — without touching the entity path. Crediting its observation would false-*positive*
  a guess. The fix must credit *data-retrieval* observations and exclude
  *introspection* ones.
- **Surgical, deterministic, hermetic.** No change to the binary gates, no new
  dependency; pure substring scan as today, just over a correct haystack.

## Considered options

1. **Grade query text + data-retrieval observation; exclude schema-introspection
   observations.** *Chosen.* A new `traversal_text(entry)` = the action (always) +
   the response excerpt **iff** the entry is not a catalog/introspection call
   (`is_schema_introspection`: postgres-mcp `list_schemas`/`list_objects`/
   `get_object_details`, or a Cypher `CALL db.labels/relationshipTypes/propertyKeys/
   schema`). Credits genuine traversal regardless of typed-vs-untyped phrasing;
   the introspection exclusion blocks the catalog false-positive.
2. **Action-only, but require typed queries via the skill prompt.** *Rejected.*
   A prompt nudge can't make the metric *valid* — untyped enumeration is legitimate
   (often superior) traversal; the metric, not the agent, is wrong. Empirically
   prompt-only fixes slip (cf. ADR-0022).
3. **Add node-name traversal markers to the fixture.** *Rejected.* The fixture
   deliberately uses relationship-type markers, not node names — "an agent can
   traverse *to* a node via relationships without ever querying it by name." Adding
   names re-introduces the recall/trajectory conflation the design separated.
4. **Scan all observations, no introspection exclusion.** *Rejected.* Lets
   `CALL db.relationshipTypes()` alone score `trajectory=1.0` — a guess credited as
   a walk. The exclusion is load-bearing.

## Decision

- Add `traversal_text(entry)` and `is_schema_introspection(entry)` to
  `evaluation/_text.py`. `traversal_text` = `statement_text` (the action) + the
  `response_excerpt` for non-introspection entries.
- `needle.score_workup` builds its `queries_lower` haystack from `traversal_text`,
  so **both** `trajectory` and the per-edge supporting-fact `ledger_markers` grade
  the (action, observation) pair.
- `statement_text` is **unchanged** (query-only); reconciliation's "both stores
  queried" check is about the *action* and keeps using it.

## Consequences

- The trajectory/supporting-fact scores become **phrasing-invariant**: an agent
  that retrieves the bridge edges scores `grounded=True` whether it names the
  relationship types in the query or reads them off the returned data. The
  2026-06-07 Halberd run re-scores `trajectory=1.00`, `grounded=True`.
- A genuine guess still fails: naming the bridge in the note with **no** ledger
  query that retrieves those edges leaves the markers absent from every
  (action, observation) → `trajectory=0`. Schema enumeration alone never credits
  traversal.
- `recall` and the binary citation/governance gates are untouched; this only
  corrects the traverse-vs-guess signal. Deterministic, hermetic, no new dependency.

## Sources

- SoK: Agentic RAG — trajectory/observation-aware evaluation — https://arxiv.org/abs/2603.07379
- AgenticRAGTracer — hop-aware multi-step retrieval diagnosis — https://arxiv.org/html/2602.19127v1
- Planted-needle harness + the traverse-vs-guess criterion — [docs/research/analytic-rigor-eval.md](../../research/analytic-rigor-eval.md)
