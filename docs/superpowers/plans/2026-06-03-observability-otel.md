# Observability (OpenTelemetry) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox (`- [ ]`) steps.

**Goal:** Instrument the harness with OpenTelemetry traces + metrics (GenAI semantic conventions) so a run reports task duration, time-to-report, evidence-query volume, accuracy, and citation/tradecraft compliance — mostly by *surfacing already-computed artifacts* as telemetry, plus new timing. (ROADMAP Phase 5.)

**Architecture:** `src/ariadne/observability.py` imports only `opentelemetry-api` (no-op until an SDK is configured — OTel library guidance), exposes a `workup_span()` context manager (a GenAI `invoke_agent` span whose duration = task time), metric instruments, `record_workup_metrics()` (emits from the existing `CitationReport`/`TradecraftReport`/`ProvenanceLedger`), and `setup_telemetry()` (configures the SDK + OTLP exporter from env, called by the CLI/MCP entry points; no-op without the `otel` extra). The SDK lives in dev (tests) + the `otel` extra (export).

**Tech Stack:** Python 3.14, `uv`, `ruff`, `pytest`; `opentelemetry-api` (core), `opentelemetry-sdk` (dev + `otel` extra), `opentelemetry-exporter-otlp` (`otel` extra). Tests use in-memory exporters. ENV: pytest is `uv run python -m pytest …`.

> **Grounding (June 2026, verified):** OTel GenAI semantic conventions — span tree `invoke_agent` → `chat` → `execute_tool`, `gen_ai.*` attributes; libraries depend on `-api` only (no-op until SDK configured), apps configure the SDK; test with `InMemorySpanExporter` + `SimpleSpanProcessor` and `InMemoryMetricReader`. The Claude Agent SDK emits its own LLM-call spans via `CLAUDE_CODE_ENABLE_TELEMETRY=1`. → ADR-0010.

> **Commits:** plain messages, NO Co-Authored-By / "Generated with" / 🤖. Gate: `make lint && uv run python -m pytest tests/unit tests/test_smoke.py -q`.

---

### Task 1: `observability.py` + deps + hermetic tests

**Files:**
- Modify: `pyproject.toml` (`opentelemetry-api>=1.30` in `[project] dependencies`; `opentelemetry-sdk>=1.30` in the dev group; `otel = ["opentelemetry-sdk>=1.30", "opentelemetry-exporter-otlp>=1.30"]` extra), `uv.lock`
- Create: `src/ariadne/observability.py`
- Test: `tests/unit/test_observability.py` (hermetic, in-memory exporters)

- [ ] **Step 1: Add deps.** `pyproject.toml`: add `"opentelemetry-api>=1.30"` to `[project] dependencies`; add `"opentelemetry-sdk>=1.30"` to the `[dependency-groups] dev` list (needed for tests); add `otel = ["opentelemetry-sdk>=1.30", "opentelemetry-exporter-otlp>=1.30"]` under `[project.optional-dependencies]`. `uv lock`, then `uv sync --group dev` so the SDK is importable for the tests.

- [ ] **Step 2: Hermetic test** (`tests/unit/test_observability.py`) — in-memory span + metric capture:

```python
from __future__ import annotations

import pytest
from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


@pytest.fixture(scope="module", autouse=True)
def _otel_providers():
    # set-once global providers with in-memory readers (OTel allows one set)
    exporter = InMemorySpanExporter()
    tp = TracerProvider()
    tp.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(tp)
    reader = InMemoryMetricReader()
    metrics.set_meter_provider(MeterProvider(metric_readers=[reader]))
    pytest._otel_exporter = exporter  # type: ignore[attr-defined]
    pytest._otel_reader = reader  # type: ignore[attr-defined]
    yield


def _spans():
    return pytest._otel_exporter.get_finished_spans()  # type: ignore[attr-defined]


def test_workup_span_emits_invoke_agent_with_attributes() -> None:
    from ariadne.observability import workup_span

    pytest._otel_exporter.clear()  # type: ignore[attr-defined]
    with workup_span("Halberd", "synthetic", semantic=True):
        pass
    spans = _spans()
    assert any(s.name == "invoke_agent" for s in spans)
    s = next(s for s in spans if s.name == "invoke_agent")
    assert s.attributes["gen_ai.agent.name"] == "ariadne"
    assert s.attributes["ariadne.dataset"] == "synthetic"
    assert s.attributes["ariadne.entity"] == "Halberd"


def test_record_workup_metrics_sets_span_attrs_and_records() -> None:
    from ariadne.observability import record_workup_metrics, workup_span
    from ariadne.provenance.citations import CitationReport
    from ariadne.provenance.ledger import ProvenanceLedger
    from ariadne.provenance.tradecraft import lint_estimative_language

    pytest._otel_exporter.clear()  # type: ignore[attr-defined]
    led = ProvenanceLedger()
    led.record("mcp__neo4j__read_neo4j_cypher", {"query": "Q"}, "ex")
    report = CitationReport(ok=False, cited=["g1"], dangling=[], unused=[], uncited=["x"])
    tc = lint_estimative_language("Halberd is likely the lead.")
    with workup_span("Halberd", "synthetic"):
        record_workup_metrics(entity="Halberd", dataset="synthetic", duration_s=1.5,
                              report=report, tradecraft=tc, led=led)
    s = next(s for s in _spans() if s.name == "invoke_agent")
    assert s.attributes["ariadne.evidence_calls"] == 1
    assert s.attributes["ariadne.citation.ok"] is False
    assert s.attributes["ariadne.citation.uncited"] == 1


def test_setup_telemetry_is_noop_without_endpoint(monkeypatch) -> None:
    from ariadne import observability

    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    assert observability.setup_telemetry() is False
```

(Note: `record_workup_metrics`'s ledger param is named `led` to match the test; the SDK's set-once provider means the fixture is module-scoped + `.clear()` between tests.)

- [ ] **Step 3: run** → FAIL (no `ariadne.observability`).

- [ ] **Step 4: Implement** `src/ariadne/observability.py`:

```python
"""OpenTelemetry instrumentation — traces + metrics for the harness (ROADMAP Phase 5).

Follows the OpenTelemetry GenAI semantic conventions. Imports only
``opentelemetry-api`` (no-op until an SDK is configured — OTel's library
guidance), so the base install emits nothing. The SDK + OTLP exporter are the
optional ``otel`` extra, configured by the application entry points via
``setup_telemetry()``. Emits a top-level ``invoke_agent`` span per workup (its
duration = task time) and metrics for query volume + citation/tradecraft
compliance — most of which Ariadne already computes. See ADR-0010.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import TYPE_CHECKING

from opentelemetry import metrics, trace

if TYPE_CHECKING:
    from collections.abc import Iterator

    from ariadne.provenance.citations import CitationReport
    from ariadne.provenance.ledger import ProvenanceLedger
    from ariadne.provenance.tradecraft import TradecraftReport

_tracer = trace.get_tracer("ariadne")
_meter = metrics.get_meter("ariadne")

# No-op until a MeterProvider is configured; proxy instruments route to it later.
_workups = _meter.create_counter("ariadne.workups", description="Workups run.")
_duration = _meter.create_histogram(
    "ariadne.workup.duration", unit="s", description="Workup wall-clock time."
)
_evidence = _meter.create_counter(
    "ariadne.evidence.calls", description="Evidence-store tool calls per workup."
)
_failures = _meter.create_counter(
    "ariadne.citation.failures", description="Citation-gate failures per workup."
)


@contextmanager
def workup_span(
    entity: str, dataset: str, *, semantic: bool = False, sql: bool = False
) -> Iterator[trace.Span]:
    """A GenAI ``invoke_agent`` span wrapping a workup; its duration is the task time."""
    with _tracer.start_as_current_span(
        "invoke_agent",
        attributes={
            "gen_ai.operation.name": "invoke_agent",
            "gen_ai.agent.name": "ariadne",
            "ariadne.dataset": dataset,
            "ariadne.entity": entity,
            "ariadne.semantic": semantic,
            "ariadne.sql": sql,
        },
    ) as span:
        yield span


def record_workup_metrics(
    *,
    entity: str,
    dataset: str,
    duration_s: float,
    report: CitationReport,
    tradecraft: TradecraftReport,
    led: ProvenanceLedger,
) -> None:
    """Emit metrics + enrich the current span from the already-computed artifacts."""
    attrs = {"ariadne.dataset": dataset}
    n_calls = len(led.entries)
    fails = len(report.uncited) + len(report.dangling) + len(report.unsupported)
    _workups.add(1, attrs)
    _duration.record(duration_s, attrs)
    _evidence.add(n_calls, attrs)
    if fails:
        _failures.add(fails, attrs)
    span = trace.get_current_span()
    span.set_attribute("ariadne.evidence_calls", n_calls)
    span.set_attribute("ariadne.citation.ok", report.ok)
    span.set_attribute("ariadne.citation.uncited", len(report.uncited))
    span.set_attribute("ariadne.citation.unsupported", len(report.unsupported))
    span.set_attribute("ariadne.tradecraft.estimative_terms", len(tradecraft.standard_terms))
    span.set_attribute("ariadne.tradecraft.has_confidence", tradecraft.has_confidence_statement)


def setup_telemetry() -> bool:
    """Configure the SDK + OTLP export from env if the ``otel`` extra is installed.

    No-op (returns False) when the SDK/exporter aren't installed or no
    ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set — so the api-only core emits nothing.
    """
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return False
    try:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        return False
    resource = Resource.create({"service.name": "ariadne"})
    tp = TracerProvider(resource=resource)
    tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tp)
    metrics.set_meter_provider(
        MeterProvider(
            resource=resource,
            metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
        )
    )
    return True
```

- [ ] **Step 5: run** `uv run python -m pytest tests/unit/test_observability.py -q` → 4 passed. `make lint` clean. (If the set-once provider causes a second-set warning across the suite, keep the fixture module-scoped; if another test file also sets providers, scope this fixture so it's the only setter — there are no other OTel tests.)

- [ ] **Step 6: full suite + lint + commit.** `feat(observability): OTel instrumentation core (workup span + metrics + setup)`

---

### Task 2: wire into the workup loop + entry points

**Files:**
- Modify: `src/ariadne/cli.py` (`run_workup`: time + span + metrics; `main`: call `setup_telemetry()`), `src/ariadne/mcp_server.py` (`main`: call `setup_telemetry()`)
- Test: `tests/unit/test_cli_observability.py`

- [ ] **Step 1: Failing test** — verify `run_workup` records metrics. Since `run_workup` runs the live agent loop, test the thin seam: confirm `run_workup` is wrapped (call it with the agent `query` monkeypatched to yield nothing + stores absent → it still emits a span with the entity). Simpler/robust: assert that `cli.main` calls `setup_telemetry` and that `run_workup` uses `workup_span`. Pragmatic test:

```python
from __future__ import annotations

import ariadne.cli as cli


def test_main_calls_setup_telemetry(monkeypatch) -> None:
    called = {}
    monkeypatch.setattr("ariadne.cli.setup_telemetry", lambda: called.setdefault("yes", True) or False)
    # index path needs no API key and returns fast if stores absent -> but we only
    # need to reach the setup call; use eval which is pure + no key:
    monkeypatch.setattr("ariadne.cli._run_eval", lambda *a, **k: 0)
    cli.main(["eval", "/tmp/nope", "--fixture", "halberd"])
    assert called.get("yes")
```
(Adapt to where you place the `setup_telemetry()` call in `main` — it should run once near the top of `main`, before dispatch, so every subcommand gets telemetry.)

- [ ] **Step 2: Implement**
  - `cli.py`: import `from ariadne.observability import record_workup_metrics, setup_telemetry, workup_span`. In `main`, call `setup_telemetry()` once near the top (after `load_dotenv`). In `run_workup`, wrap the agent loop in `with workup_span(entity, dataset, semantic=with_semantic, sql=with_sql):`, time it with `time.monotonic()` around the `async for` loop, and after `validate_citations`/`lint_estimative_language` call `record_workup_metrics(entity=entity, dataset=dataset, duration_s=elapsed, report=report, tradecraft=tradecraft, led=ledger)`. Also `print` the duration in the existing summary line ("… in 12.3s").
  - `mcp_server.py`: in `main()`, call `setup_telemetry()` before `mcp.run()`.

- [ ] **Step 3: run** the new test + full suite → green. `make lint` clean.

- [ ] **Step 4: Commit** `feat(observability): wire workup timing + metrics + setup into CLI/MCP entry points`

---

### Task 3: ADR-0010 + docs + ROADMAP done

**Files:** `docs/architecture/decisions/0010-observability-opentelemetry.md`, `docs/architecture/decisions/index.md`, `zensical.toml`, `README.md`, `IMPL.md`, `ROADMAP.md`

- [ ] **Step 1:** Write **ADR-0010** (MADR, mirror existing): decision = OpenTelemetry GenAI semantic conventions; `-api` core / sdk+otlp in `otel` extra; emit the already-computed artifacts (query count, citation/tradecraft compliance, eval accuracy) + new timing; complements the Claude Agent SDK's `CLAUDE_CODE_ENABLE_TELEMETRY`. Options considered: OTel (chosen) vs vendor SDK (lock-in) vs custom logging (no standard). Add the index row + nav entry.
- [ ] **Step 2:** `README.md` — short "Observability" note: `uv sync --extra otel`, set `OTEL_EXPORTER_OTLP_ENDPOINT` (+ optionally `CLAUDE_CODE_ENABLE_TELEMETRY=1` for the SDK's LLM-call spans); spans/metrics emitted (`invoke_agent` span, duration/query/compliance metrics).
- [ ] **Step 3:** `IMPL.md` — "Observability shipped" entry. `ROADMAP.md` — mark the Phase 5 observability item `[x]` (done 2026-06-03), referencing ADR-0010 + this plan.
- [ ] **Step 4:** `uv run --with zensical zensical build` → "No issues found". Commit `docs: ADR-0010 observability (OpenTelemetry) + enable instructions; ROADMAP done`.

---

## Done (all true)
1. `observability.py` emits an `invoke_agent` span (duration = task time) + metrics (workups, duration, evidence calls, citation failures); api-only core is no-op until `setup_telemetry()` configures the SDK from env.
2. `run_workup` is timed + instrumented; CLI/MCP `main` call `setup_telemetry()`.
3. Hermetic tests (in-memory exporters) green; `make lint` + full suite green.
4. ADR-0010 + README enable-instructions; ROADMAP Phase-5 item done.

## Manual smoke
`uv sync --extra otel`; run an OTLP collector (or `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318`); `ariadne workup … --semantic` → traces (invoke_agent + duration) + metrics land in the collector. With `CLAUDE_CODE_ENABLE_TELEMETRY=1`, the SDK's per-LLM-call spans nest under it.
