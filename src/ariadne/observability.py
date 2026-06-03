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
