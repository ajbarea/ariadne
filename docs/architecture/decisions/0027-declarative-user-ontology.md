# 0027, Declarative user ontology — a lightweight TOML vocabulary the mapper maps *into*

- **Status:** Accepted (2026-06-07)
- **Deciders:** Ariadne maintainers
- **Refines:** [ADR-0020](0020-adaptive-self-improving-ariadne.md) (axis A2, the semantic layer) · builds on [ADR-0026](0026-llm-schema-mapper.md) (the agentic mapper) + [ADR-0025](0025-applying-a-ratified-mapping.md) (apply)

## Context

A1 maps a user's introspected schema onto Ariadne's canonical schema where the
entity/relationship `type` is an **open string** — the mapper "picks the most
natural one" (`person` / `org` / `MEMBER_OF` / …) with nothing constraining it.
That is right for a generic first draft, but a real analyst works in a *domain*:
their world is `Vessel` / `Berth` / `MOORED_AT`, or `Indicator` / `Campaign` /
`ATTRIBUTED_TO` — a closed vocabulary they want the graph to speak, not whatever
synonym the model reached for this run.

A2 is that semantic layer: let a user **declare their own entity-type +
relationship vocabulary**, and have the mapper map *into that* — every entity
typed as one of their declared types, every relationship one of their declared
edges routed `domain → range`. The contestable questions are (a) what the user
declares it *in*, and (b) how the closed vocabulary is *enforced*. Hence this ADR.

## Decision drivers

- **A closed vocabulary is only worth declaring if it's enforced.** The mapper
  must be constrained to the declared types and *verified* against them, not merely
  nudged. June-2026 ontology-aligned extraction makes schema-compliant type
  assignment a validated property, not a hope (Anchor, OntoLogX).
- **Intrinsic-vs-relational routing is the declarative core.** Every property is
  either an intrinsic attribute (a node column) or a relational edge (OntoKG).
  Ariadne's `Mapping` already separates `attribute_columns` from `relationships`;
  the ontology only has to declare *which edge types are legal and what they
  connect*, so the routing decision becomes a typed, checkable claim.
- **Stay in Ariadne's idiom, stay lean.** Every config surface here is TOML
  (`mapping.toml`, the `[dataset]` header, profiles). A user's vocabulary is a
  handful of names — it should not drag in a modeling framework or a second
  serialization language.
- **SHACL-validatable later, by construction.** The note in ADR-0020 promises
  SHACL validation eventually; the declared shape must transpile *mechanically*
  to SHACL node/property shapes when that lands, so the format has to line up with
  SHACL's concepts (a node shape per entity type, a property shape per
  relationship type with `sh:class` domain/range).
- **Reuse the shipped spine.** Forced tool-use + a bounded, validator-terminated
  retry loop already exist (ADR-0026). The ontology should ride them — constrain
  the tool schema, feed ontology violations back as repair errors — not add a
  parallel mechanism.

## Considered options

1. **Keep open-string types; no ontology (status quo).** *Rejected.* It gives the
   user no control over their domain vocabulary, lets the model invent a different
   type each run, and produces nothing portable or contestable at the user's level.
   It is the thing A2 exists to fix.
2. **Adopt LinkML (YAML) as the declaration format.** *Considered, deferred.*
   LinkML is the 2026 reference data-modeling framework: one YAML model is the
   single source of truth that generates OWL, SHACL, and JSON Schema, and OntoGPT /
   SPIRES already turn LinkML schemas into extraction prompts. But its strengths are
   redundant or premature here — its LLM-extraction value duplicates the
   forced-tool-use loop we already ship; its SHACL generation is the *"later"* we
   can reach with a ~30-line transpiler; and it costs a heavy transitive dependency
   tree plus a YAML idiom break from our all-TOML config, to model classes / slots /
   mixins / inheritance that a name-and-domain-range vocabulary does not need
   (speculative generality, YAGNI). Recorded as the upgrade path if the ontology
   ever needs imports, inheritance, or multi-target codegen.
3. **Full OWL/RDF ontology + a reasoner.** *Rejected.* Open-world description-logic
   reasoning and a reasoner dependency are far past "a user names a dozen types."
   Closed-world SHACL-style structural validation is the right minimum (OntoLogX's
   stage 2: syntactic → SHACL compliance → semantic), and we get there without
   importing a reasoner.
4. **Large-ontology search-and-navigate** (Anchor's hybrid ontology discovery over
   UCO/STIX-scale schemas). *Deferred.* That solves *scale* — ontologies too large
   to fit in a prompt, where prompt-based schema inclusion is exactly what breaks.
   A user's lightweight declared vocabulary fits in the prompt and the tool schema,
   so prompt/enum inclusion is the correct tool now; navigate-a-huge-ontology is the
   deferred large path, mirroring ADR-0026's AutoLink deferral for large *schemas*.
5. **A lightweight `ontology.toml` — declared entity types + relationship types
   (with `domain`/`range`), enum-injected into the forced-tool schema, enforced by
   a deterministic `validate_against_ontology` inside the existing repair loop, and
   designed to transpile mechanically to SHACL.** *Chosen.*

## Decision

Adopt **option 5**.

- **The artifact.** A user writes an `ontology.toml`: an array of `[[entity_types]]`
  (`name`, optional `description`) and an array of `[[relationship_types]]`
  (`name`, `domain`, `range` — the from/to entity-type names — and optional
  `description`). `mapping/ontology.py` loads it into frozen `EntityType` /
  `RelationshipType` / `Ontology` dataclasses. `domain`/`range` are single
  entity-type names in v1 (matching the 1:1 foreign-key→edge reality and the
  baseline's output); multi-domain/range is the deferred `sh:or` extension.
- **Enforcement — `validate_against_ontology(mapping, ontology) -> list[str]`.**
  Deterministic, pure, returns structural-style errors: every entity `type` must be
  a declared entity type; every relationship `type` must be a declared relationship
  type; and each relationship's endpoints must obey the declared routing — the
  `from_table`'s entity type must equal the edge's `domain`, the `to_table`'s the
  `range`. (Endpoints that aren't mapped at all are left to the existing structural
  `validate_mapping`, so the two validators compose without double-reporting.) This
  is the relational half of intrinsic-vs-relational routing made checkable.
- **Guidance — enum-constrained forced tool-use.** When an ontology is present,
  `build_map_tool(ontology)` injects the declared names as JSON-Schema `enum`s on
  the entity/relationship `type` fields, and `build_mapping_prompt` describes the
  vocabulary (types + the legal `domain → range` edges). The enum hard-constrains
  the model's *structured output* to the vocabulary (constrained generation); the
  validator catches the routing the enum can't express (which `domain`/`range` a
  given edge connects). This is prompt-based schema inclusion — correct for a small
  user ontology.
- **The loop.** `propose_with_repair` takes the optional `ontology` and runs
  `validate_mapping` **and** `validate_against_ontology`, re-prompting with the
  union of complaints until the proposal is both loadable *and* ontology-conformant
  or the bound is hit — the same deterministic-gate-terminates-the-loop stance as
  ADR-0026, now extended to ontology conformance.
- **CLI + the baseline/LLM split.** `ariadne map --ontology PATH` loads the
  ontology, configures the mapper, and validates against it. The LLM mapper is
  *guided* by the vocabulary (enum + prompt). The deterministic baseline cannot
  invent a user's vocabulary from table names, so for it the ontology is a
  **validation-only** layer — it still proposes its heuristic draft, and the
  ontology violations are reported for the human to resolve. Ontology *guidance* is
  honestly an LLM capability; ontology *enforcement* is available to both.

## Consequences

- **A2's first slice closes.** A user maps their store into *their own* domain
  vocabulary, type-checked and routing-checked before a human ever sees the draft,
  through the unchanged ADR-0025 freeze→apply path. The open-string default still
  works when no `--ontology` is given.
- **SHACL is now a mechanical transpile, deferred not blocked.** Entity types →
  `sh:NodeShape`, relationship types → `sh:PropertyShape` with `sh:class`
  domain/range; the TOML was shaped to line up. When SHACL validation lands it
  replaces/augments `validate_against_ontology`, it doesn't restructure anything.
- **No new dependency; the idiom holds.** The ontology is TOML parsed by the
  stdlib `tomllib`, like every other config artifact. LinkML stays the documented
  upgrade path, not a cost we pay now.
- **Large-ontology navigation is deferred,** the same way large-schema exploration
  is (ADR-0026) — both slot in behind the same seams when a user brings something
  that doesn't fit a prompt.
- **One honest asymmetry:** the deterministic baseline gains validation but not
  guidance, so `--ontology` without `--llm` will usually surface violations rather
  than a conformant draft. That is the truthful capability line, and it is
  documented in the command's help.

Sources: intrinsic-vs-relational routing + portable declarative schema — OntoKG,
[arXiv:2604.02618](https://arxiv.org/abs/2604.02618); SHACL-enforced schema-compliant
typing + prompt-inclusion fails only at large-ontology scale — Anchor,
[arXiv:2606.01208](https://arxiv.org/abs/2606.01208); validator-driven correction
(syntactic → SHACL compliance → semantic) — OntoLogX,
[arXiv:2510.01409](https://arxiv.org/abs/2510.01409); deferred-correction token
tradeoff (considered for the loop) — Better Later Than Sooner,
[arXiv:2605.29168](https://arxiv.org/abs/2605.29168); the heavier single-source-of-truth
alternative — LinkML, [arXiv:2511.16935](https://arxiv.org/abs/2511.16935).
