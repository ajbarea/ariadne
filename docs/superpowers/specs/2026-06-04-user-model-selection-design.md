# Ariadne — design: user-selectable model profiles

> **Status:** design, approved 2026-06-04, awaiting spec review.
> **Driver:** Users should be able to swap the model that runs a workup. Today
> model selection is deployment-env-only (`ANTHROPIC_BASE_URL` + `ANTHROPIC_MODEL`
> + the LiteLLM routing config); no `model` parameter exists on the MCP `workup`
> tool, the CLI `workup` command, or the Claude Code plugin.
> **Builds on:** [ADR-0012](../../architecture/decisions/0012-cloud-vs-air-gapped-deployment-fork.md)
> (the single-seam model fork) and the air-gap governance posture it establishes.

## Goal

Let a user pick *which model* runs a workup, per call, **from a curated allowlist
the operator defines** — without letting an analyst select a cloud model inside an
air-gapped enclave, and without forking the analytic logic. Litmus test:
*`ariadne workup <entity> --profile fast-local` runs qwen3 locally; `--profile
rigorous` runs cloud Claude; an undefined profile errors with the valid names; an
air-gap deployment that lists no cloud profile makes a cloud selection impossible.*

## Why curated profiles (not a free-form model string)

A raw `model="..."` per-call param maximises flexibility but punches a hole in the
governance posture: an analyst could request a cloud model inside an enclave (the
egress leak [ADR-0012](../../architecture/decisions/0012-cloud-vs-air-gapped-deployment-fork.md)
exists to prevent), and raw Ollama/LiteLLM tags would leak into the analytic
interface. A **curated, operator-defined allowlist** gives users real choice within
vetted options; air-gap governance is preserved *by construction* — the operator
simply does not define a cloud profile, so the analyst literally cannot name one.

## Decisions

### D1 — Profile registry (Ariadne-owned allowlist)

A profile is `{name, model, egress, description}`:
- `name` — what the user selects (`fast-local`, `rigorous`, `air-gap`).
- `model` — the identifier handed to `ClaudeAgentOptions(model=...)`; routes through
  whatever `ANTHROPIC_BASE_URL` points at (a LiteLLM `model_name`, or a direct
  Anthropic model id). `None` for the built-in `default` profile.
- `egress` — advisory governance class (`none` | `anthropic` | `<provider>`),
  surfaced for audit. **Not** a runtime network control (see Non-goals).
- `description` — shown by `ariadne profiles` / `list_profiles()`.

The registry is **Ariadne-side** (not derived from LiteLLM's `/v1/models`) so it is
deployment-agnostic: it works whether the backend is LiteLLM→Ollama, direct
Anthropic, vLLM, or OpenRouter, and the allowlist lives where Ariadne can enforce
it. A pure resolver:

```
resolve_profile(name, registry) -> Profile        # unknown name -> ValueError listing valid names
load_profiles(env) -> dict[str, Profile]           # built-in default + optional TOML override
```

**Built-in default:** a single `default` profile with `model=None` — sets no model,
so behaviour is byte-identical to today (zero regression when no profile is given).

**Operator override:** `ARIADNE_PROFILES` points at a TOML file; a committed
`infra/profiles.example.toml` ships `default` plus commented `fast-local` /
`rigorous` / `air-gap` examples. When the env var is unset, only `default` exists.

### D2 — Threading (no fork in analytic logic)

- `build_options(..., model: str | None = None)` sets `ClaudeAgentOptions(model=...)`
  **only** when `model` is not `None`; otherwise the field is omitted and the SDK
  default / env applies. (Verified 2026-06-04: `ClaudeAgentOptions` exposes a
  top-level `model` field.)
- `run_workup(..., profile: str = "default")` resolves the profile once, passes the
  resolved `model` to `build_options`, and records the profile for governance.
- One resolve point; the agent loop, skills, connectors, gates, and eval are
  untouched. Cloud and air-gap deployments run the same code.

### D3 — Surfaces

- **CLI:** `ariadne workup --profile <name>`; new `ariadne profiles` subcommand
  listing `name`, `egress`, and `description`.
- **MCP:** `workup(entity, dataset, sql, semantic, profile="default")` and a new
  `list_profiles()` tool so any MCP client can discover the allowlist.
- **Plugin:** `analyst-workup` SKILL.md documents the `profile` argument and passes
  it through; no logic added.

### D4 — Governance surfacing

The resolved profile `name` + `egress` class are written to the existing
`governance.json` artifact and attached as OpenTelemetry span attributes on the
workup span — so every analytic product is auditable for *which model and egress
class produced it*. This reuses the existing governance/observability spine
(low cost) and directly serves the brief's governance triad.

### D5 — LiteLLM config alignment

`infra/litellm/config.yaml` gains named routes (e.g. `fast-local` → `ollama_chat/qwen3:14b`,
`rigorous` → an Anthropic passthrough) alongside the wildcard, so the proxy's
`model_name`s match the profile `model` identifiers. Documented in
`infra/litellm/README.md`.

## Non-goals (YAGNI)

- **No network egress enforcement.** This builds selection + allowlist + audit, not
  outbound-network blocking. The hard air-gap guarantee remains operator curation;
  actual egress *enforcement* (network policy + a no-egress CI guard) is the
  separate ADR-0012 follow-up.
- **No per-profile tuning** (temperature, max-tokens, system-prompt variants). A
  profile selects a model, nothing more, until a use case demands otherwise.
- **No `fallback_model` wiring** yet (the SDK field exists; not needed for v1).

## Testing (TDD, hermetic — no live model)

- `resolve_profile`: valid → model; unknown → `ValueError` enumerating valid names;
  `default` → `None`; TOML load merges/overrides built-ins; an air-gap registry
  (no cloud profile) rejects a cloud name.
- `build_options`: sets `model` iff the profile resolves to one; omits it for
  `default`.
- `run_workup`/MCP/CLI: arg plumbing smoke; governance.json records the profile.
- Lint stable with and without optional extras.

## Decision record

This is a contestable architectural choice (curated allowlist, Ariadne-owned
registry, audit-not-enforce governance) → **ADR-0013**, superseding nothing,
relating to ADR-0012.
