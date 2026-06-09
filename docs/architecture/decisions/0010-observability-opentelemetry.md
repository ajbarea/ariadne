# 0010, Observability via OpenTelemetry (GenAI semantic conventions)

- **Status:** Accepted (2026-06-03)
- **Deciders:** Ariadne maintainers
- **Relates to:** [ADR-0001](0001-orchestration-on-claude-agent-sdk.md) (Ariadne runs on the Claude Agent SDK, which has its own OTEL integration)

## Context

As the harness matures we need runtime visibility into the MCP server and the
workup loop: **task duration** (time-to-report), **query volume** (how many
evidence calls per run), **analytic accuracy** (citation coverage, entailment
precision, eval scores), and **governance compliance** (ICD-203 tradecraft,
uncited/dangling claims). Without traces and metrics these properties are only
observable through the file artifacts (`citations.json`, `tradecraft.json`,
eval output), there is no cross-run dashboard, no latency baseline, and no
hook into a shared observability stack when Ariadne is deployed inside a larger
environment.

## Decision drivers

- **Vendor-neutral / cross-backend**: the same instrumentation should export
  to Datadog, Google Cloud Trace, AWS X-Ray, Azure Monitor, Jaeger, Grafana,
  and the Claude Agent SDK's own telemetry without a code change.
- **Reuse signals Ariadne already computes**: most metrics of interest are
  already computed: query count (provenance-ledger `gN`), citation
  coverage/precision, tradecraft compliance, eval scores. We are surfacing
  them as telemetry, not recomputing them.
- **Zero cost at the base install**: operators who do not configure an OTLP
  endpoint must not pay any runtime overhead.
- **Standard so it composes**: the Claude Agent SDK already emits OTEL via
  `CLAUDE_CODE_ENABLE_TELEMETRY=1`; Ariadne's spans should nest under those
  naturally, not create a parallel, incompatible trace tree.

## Considered options

### A. OpenTelemetry, GenAI semantic conventions (chosen)

- **Pros:**
  - CNCF-backed standard; Datadog, Google, AWS, Azure, Grafana, and Jaeger all
    consume OTLP natively.
  - The emerging `gen_ai.*` attribute family + `invoke_agent` / `execute_tool`
    / `chat` span kinds are purpose-built for agentic LLM systems.
  - `opentelemetry-api` ships a **no-op implementation**: without the SDK
    configured, every span/counter is a no-op and the base install is
    unaffected.
  - Composes with the Agent SDK's own telemetry (`CLAUDE_CODE_ENABLE_TELEMETRY=1`):
    the SDK's per-LLM-call spans nest under Ariadne's `invoke_agent` span
    automatically when both use the same OTLP pipeline.
  - Isolated in the optional `otel` extra, operators that want telemetry add
    `uv sync --extra otel`; everyone else ignores it.
- **Cons:**
  - The `gen_ai.agent.*` attribute names are still experimental; they may shift
    before the GenAI semconv reaches stability 1.0.

### B. Vendor SDK (Datadog, Langfuse, Arize, etc.)

- **Pros:** turnkey dashboards, purpose-built LLM observability views, minimal
  config.
- **Cons:** couples the harness to one backend; any operator not on that vendor
  must re-instrument. Incompatible with the cross-backend and composability
  drivers.

### C. Custom logging / JSON metrics

- **Pros:** zero new dependencies; the file artifacts (`provenance.jsonl`,
  `citations.json`, `tradecraft.json`) are already written.
- **Cons:** no distributed tracing (no trace/span correlation across calls),
  no standard exporters, no shared-stack integration, and reinvents everything
  that the OTel SDK gives for free. The artifacts are useful locally but do not
  compose with an operator's observability infrastructure.

## Decision

**Adopt A.** Emit one `invoke_agent` span per workup (duration = task time) +
per-run metrics via OpenTelemetry. The key design principle is that **most
metrics surface already-computed artifacts**: the only genuinely new
measurement is timing:

| Signal | Source | New? |
| ------ | ------ | ---- |
| Task duration / time-to-report | `run_workup` wall time | **Yes, new** |
| Evidence calls (`ariadne.evidence.calls`) | provenance-ledger `gN` count | No, existing |
| Citation failures (`ariadne.citation.failures`) | `citations.json` uncited/unsupported | No, existing |
| Tradecraft compliance (span attrs) | `tradecraft.json` estimative terms / has-confidence | No, existing |
| Governance violations (`ariadne.governance.violations` + span attrs) | `governance.json` read-only audit | No, existing |
| Workup count (`ariadne.workups`) | counter incremented per run | Minimal |
| Workup duration histogram (`ariadne.workup.duration`) | same wall time as the span | Minimal |

`opentelemetry-api` is a **core dependency** (no-op until configured).
`opentelemetry-sdk` and `opentelemetry-exporter-otlp` live in the `otel` extra
and in `dev` dependencies. `setup_telemetry()` reads
`OTEL_EXPORTER_OTLP_ENDPOINT` and wires up the SDK; if the env var is absent or
the `otel` extra is not installed, every call is a silent no-op.

## Consequences

- One OTel layer → **latency / query-volume / accuracy / governance-compliance
  dashboards** per run, exportable to any OTLP-speaking backend.
- **Base install emits nothing** (api-only no-op); the `otel` extra is an
  explicit opt-in.
- The Agent SDK's per-LLM-call spans (`chat`, `execute_tool`) nest under
  Ariadne's `invoke_agent` span when `CLAUDE_CODE_ENABLE_TELEMETRY=1` is set,
  one trace covers the full workup.
- The `gen_ai.agent.name` attribute (and peers) are marked experimental;
  flagged for review when the GenAI semconv reaches stability 1.0.
- Operators running Ariadne inside a shared OTEL pipeline (e.g. Jaeger +
  Grafana in an enterprise deployment) get Ariadne traces alongside other services
  with no extra plumbing.

## Sources

- [OpenTelemetry GenAI observability (2026)](https://opentelemetry.io/blog/2026/genai-observability/)
- [OpenTelemetry Python instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/)
