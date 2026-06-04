# 0013 — User-selectable model profiles

- **Status:** Accepted (2026-06-04)
- **Deciders:** Ariadne maintainers
- **Relates to:** [ADR-0012](0012-cloud-vs-air-gapped-deployment-fork.md) (the single-seam model fork this exposes to users)

## Context

Model selection was deployment-env-only (`ANTHROPIC_BASE_URL` + `ANTHROPIC_MODEL` +
the LiteLLM config). Users could not pick a model per workup. Naively adding a
free-form `model` parameter would break the ADR-0012 air-gap posture — an analyst
could point a workup at a cloud model from inside an enclave.

A live open-weight run (2026-06-04) also showed that a small local model needs a
*leaner loop* than a frontier model (it was throughput-bound on a large, growing
context), and that a listed profile is worthless if the model behind it cannot
actually complete a workup. Model selection must therefore carry an operating
envelope and be validatable, not just named.

## Decision

Expose a **curated profile allowlist**, Ariadne-owned. A profile binds
`{model, egress, description, envelope}` where the envelope is `{max_turns,
max_thinking_tokens}`. The built-in `default` profile sets no model (zero
regression). Operators extend the allowlist via an `ARIADNE_PROFILES` TOML; air-gap
deployments define only local profiles, so a cloud selection is impossible by
construction (an unknown name is rejected with the valid names). The profile + egress
are recorded in `governance.json` and on the OTel span for audit.

A curated allowlist is only trustworthy if every profile can actually do the job, so
`ariadne profiles --validate <name>` runs a real workup against the planted Halberd
needle under a wall-clock budget and PASSes only if it grounds in time — a
throughput-bound or incapable model FAILs. Example profiles are honest: only `default`
and `rigorous` (cloud Claude) are presented as working; local profiles are labeled
templates to validate first. Strict TOML parsing rejects unknown keys so a typo
cannot silently degrade a profile into the deployment default.

`tool_result_cap` was considered for the envelope and **rejected for v1**: the
context bulk is external `mcp__neo4j__`/`mcp__postgres__` results, the PostToolUse
hook only observes (cannot rewrite a result), and those servers carry their own
guardrails — so a uniform cap is not cleanly available and would not have helped the
measured case. Serving-side thinking-off is the larger practical win and is config.

## Consequences

- Users get real choice within vetted options; governance is preserved by curation,
  not by runtime network enforcement (which remains the separate ADR-0012 follow-up).
- A profile is `model + envelope`, so a local profile runs lean and a frontier
  profile runs generous from one codebase — no fork in the analytic logic.
- The allowlist is Ariadne-side (not derived from LiteLLM), so it works for direct
  Anthropic, LiteLLM→Ollama, vLLM, or OpenRouter backends alike.
- A profile can be proven capable before it is trusted, using the same eval harness
  that certifies the cloud baseline.
