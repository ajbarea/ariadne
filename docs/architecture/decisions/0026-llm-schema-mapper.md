# 0026, LLM-backed schema mapper — forced tool-use + a bounded, validator-terminated retry loop

- **Status:** Accepted (2026-06-07)
- **Deciders:** Ariadne maintainers
- **Refines:** [ADR-0020](0020-adaptive-self-improving-ariadne.md) (axis A1, the *agentic* mapper) · builds on [ADR-0025](0025-applying-a-ratified-mapping.md)

## Context

[ADR-0020](0020-adaptive-self-improving-ariadne.md)'s axis A1 is "schema
introspection + the agent does iterative schema-linking." The introspection,
a deterministic `BaselineMapper`, the structural validator, and the whole
freeze → apply path shipped ([ADR-0025](0025-applying-a-ratified-mapping.md)).
What is left of A1 is the **agentic** half: an LLM that *proposes* the mapping —
which tables are which canonical entity type, which columns are intrinsic
attributes vs. which foreign keys are relationships — instead of the baseline's
table-name heuristics. The mapper is already an injected `SchemaMapper` Protocol
(`propose(summary) -> Mapping`), so this adds a second implementation, not a new
seam. The design question — how the model returns the mapping, and how a wrong
proposal is corrected — is contestable, hence this ADR.

## Decision drivers

- **Structured, not free-text.** A mapping is a typed artifact; parsing prose
  into one is the brittle path. June-2026 practice for LLM structured output is
  "define a schema, add a validator, wire a repair loop."
- **The validator already exists and is deterministic.** `validate_mapping`
  catches the exact failure LLM schema-mappers make — entities that "look right"
  but can't load because a column is misnamed or an edge endpoint is unmapped.
  It should *terminate* the loop, not the model's own self-judgment.
- **Mirror what already works in this codebase.** `evaluation/judge.py` (forced
  tool-use → structured score, lazy-imported optional client) and
  `provenance/repair.py` (bounded, gate-terminated refinement over an injected
  `call_llm`) are the two proven patterns; the mapper is their composition.
- **Hermetic core.** The engine must be testable without a network or a key,
  like every other model-backed unit in the project.

## Considered options

1. **Free-text proposal, parse the prose into a `Mapping`.** *Rejected.* Brittle
   parsing, no schema guarantee, and it discards the structured-output tooling
   the API already provides.
2. **Full AutoLink-style agentic schema exploration** (the agent explores/expands
   a linked subset without ever seeing the full schema; [arXiv:2511.17190](https://arxiv.org/pdf/2511.17190)).
   *Rejected for now.* That solves *scale* — schemas too large to fit in context,
   the text-to-SQL setting. Ariadne's introspected schemas are small (a handful of
   tables) and fit in one prompt, so the multi-step exploration loop is speculative
   generality (YAGNI). Recorded as the deferred path for when a user points Ariadne
   at a large warehouse.
3. **One-shot LLM proposal, no correction.** *Rejected.* A single malformed or
   unloadable proposal then just fails the validator with no recovery, wasting the
   call and pushing every fix onto the human.
4. **Forced tool-use proposal + a bounded, validator-terminated retry loop.**
   *Chosen.*

## Decision

Adopt **option 4**, as a `ClaudeSchemaMapper` in `mapping/llm_mapper.py`
implementing the existing `SchemaMapper` Protocol.

- **Forced tool-use for structured output.** The model must call a single
  `propose_mapping` tool whose `input_schema` mirrors the `Mapping` shape
  (`entities[]` with `table`/`type`/`id_column`/`name_column`/`attribute_columns`,
  `relationships[]` with `type`/`from_table`/`to_table`/`from_column`/`to_column`).
  A pure `parse_mapping(tool_input) -> Mapping` converts it; a pure
  `build_mapping_prompt(summary, errors)` renders the schema summary, the canonical
  target, and (on a retry) the validator's complaints. This is exactly
  `judge.py`'s `submit_score` pattern.
- **Bounded, validator-terminated retry.** `propose_with_repair(summary, *, call_llm,
  max_attempts)` loops: propose → `parse_mapping` → `validate_mapping`; on a parse
  failure or any structural error it re-prompts with those errors; it stops on a
  clean validation or when `max_attempts` is hit, returning the best draft either
  way (the draft is written regardless — a human ratifies, and `propose_and_write`
  re-surfaces any residual errors). The deterministic validator is the gate, never
  the model's self-assessment — the same anti-self-refinement-degradation stance as
  `repair.py`.
- **Injected `call_llm` seam.** `propose_with_repair` takes `call_llm: Callable[[str],
  dict]` (prompt → tool input), so the loop is unit-tested hermetically with a fake
  that returns an invalid-then-valid proposal. `ClaudeSchemaMapper.propose` wires the
  real `anthropic` client (forced `propose_mapping` tool call) into that seam.
- **Optional dependency + gating.** The `anthropic` client is the new `adaptive`
  extra (lazy-imported, like `rubric`/`eval`); `ariadne map --llm` selects the Claude
  mapper over the baseline and is key-guarded (clean exit without
  `ANTHROPIC_API_KEY`). The real-model path is covered by a key/extra-gated live test,
  mirroring `test_rubric_judge_live.py`; the hermetic suite uses the fake `call_llm`.

## Consequences

- A1 closes: a maintainer can `ariadne map --llm` to get a model-proposed,
  validator-checked `mapping.toml` draft, then ratify it through the ADR-0025 apply
  path unchanged. The baseline mapper stays as the no-key, deterministic default.
- The loop self-corrects the dominant LLM-schema-mapping failure (unloadable edges /
  misnamed columns) before a human ever sees the draft, at a bounded, known cost
  (≤ `max_attempts` calls), terminated by a deterministic check rather than the
  model's own judgment.
- Large-schema scaling (AutoLink-style exploration) is explicitly deferred, not
  precluded — it would slot in behind the same `SchemaMapper` Protocol.
- One more optional extra to keep pinned; it shares the `anthropic` client with
  `rubric`.

Sources: AutoLink agentic schema linking (the deferred large-schema path) —
[arXiv:2511.17190](https://arxiv.org/pdf/2511.17190); in-depth analysis of
LLM-based schema linking —
[IBM Research, EDBT 2026](https://research.ibm.com/publications/in-depth-analysis-of-llm-based-schema-linking);
structured output = schema + validator + repair loop (2026 practice) —
[Structured Outputs: Schema Validation for Real Pipelines](https://collinwilkins.com/articles/structured-output);
bounded, deterministically-terminated refinement —
[Self-Refine, arXiv:2303.17651](https://arxiv.org/abs/2303.17651) (via [ADR-0022](0022-post-hoc-citation-repair.md)).
