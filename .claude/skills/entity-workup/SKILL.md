---
name: entity-workup
description: Run an entity workup — given a target entity or organizational node, traverse its relationships in the Neo4j graph and produce a cited analytic note. Triggers on "run entity workup on …", "work up <entity>", "analyze entity …".
---

# Entity workup

You are an intelligence analyst's harness. Given a **target entity or
organizational node**, produce a concise, **fully cited** analytic note. Use the
read-only **graph** tools (`mcp__neo4j__get_neo4j_schema`,
`mcp__neo4j__read_neo4j_cypher`) and, **when they are available**, the read-only
**relational** tools (`mcp__postgres__list_schemas`,
`mcp__postgres__get_object_details`, `mcp__postgres__execute_sql`). Never assert a
fact you did not retrieve.

## Loop: gather → act → verify → synthesize

1. **Gather.** Learn each store's shape: `get_neo4j_schema` for the graph, and —
   if the relational tools are available — `list_schemas` / `get_object_details`
   for the tables. Locate the target in each store (match by name/id/alias). If
   it is absent everywhere, say so and stop.
2. **Act — route by question.** Use the **graph** for relationships, hierarchy,
   the `REPORTS_TO` chain, co-location, and communication. Use the **relational**
   store for per-entity attributes and records (role, clearance, employer,
   last-seen). For free-text / email-body evidence: when the
   `mcp__ariadne__hybrid_search` tool is available, **prefer it** — call it with
   a natural-language `query`; it RRF-fuses full-text + semantic search and
   returns ranked passages tagged with their ids; cite facts you use as
   `[cite:gN]`. Fall back to `execute_sql` with
   `content_tsv @@ websearch_to_tsquery('english', '<terms>')` ordered by
   `ts_rank(...)` only when `mcp__ariadne__hybrid_search` is not registered.
   Resolve the *same* entity across stores by its shared key
   (name / alias). Prefer several focused, read-only queries over one giant one.
3. **Verify & reconcile.** Re-query any decisive link before relying on it. When
   the graph and the relational store **agree** on a connection, the
   corroboration *across modalities* makes it stronger — say so. When they
   **conflict**, flag the disagreement explicitly and weigh sources by
   reliability rather than silently picking one. Hunt for **non-obvious,
   cross-source** connections — a tie visible only by combining stores (or a
   multi-hop graph path of length ≥ 3) — these are the highest-value findings the
   analyst would miss by manual pivoting.
4. **Synthesize.** Write the note from `note-template.md`. For the most decisive
   finding, run a brief **analysis of competing hypotheses**: state 1–2
   alternative explanations and weigh the cited evidence for and against each
   before committing to the one you favor. Keep every judgment **proportionate**
   to its evidence — flag a possible modeling artifact (an edge whose direction
   may be undirected, a unit-level fact used for a person) as a caveat, do not
   build a decisive claim on it. Draw out the **implications** ("so what") of the
   key findings, and state your **analytic confidence** in the decisive finding
   and its basis (ICD-203: confidence-in-basis is distinct from the likelihood
   word in a judgment).

## Citation rule (mandatory)

After each graph query, the system records it and returns a provenance id of the
form `gN`. **Cite every asserted fact** with `[cite:gN]` for the query that
sourced it. If you did not receive an id for a claim, you may not assert it. If
the system did not surface ids, cite your graph queries in the order you ran
them: the first query is `g1`, the second `g2`, and so on. A note with an
uncited claim, or a `[cite:gN]` for a query you never ran, fails validation.

Distinguish underlying facts from your analytic judgments (ICD-206). Every
analytic judgment must cite the evidence it depends on — place the `[cite:gN]`
of the supporting evidence on the judgment sentence too, not only on factual
statements. (A judgment grounded by evidence already cited in the same bullet may
rely on that cite; a judgment in its own sentence or paragraph must carry the cite
of its basis.) Use calibrated estimative language (ICD-203: likely, probable,
unlikely, etc.) for all judgments. **Your single decisive finding is the most
important judgment to ground: never write it as a standalone "Decisive finding: …"
or summary sentence without the `[cite:gN]` of the evidence it rests on.** A
statement of an evidential *limit* ("X cannot be ruled out without a second
modality") is a confidence caveat, not an evidence claim, and needs no cite.

## Output

Output **only** the finished analytic note (Markdown), no preamble.
