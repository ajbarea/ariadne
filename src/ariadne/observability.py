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

    from ariadne.evaluation.needle import EvalReport
    from ariadne.profiles import Profile
    from ariadne.provenance.citations import CitationReport
    from ariadne.provenance.governance import GovernanceReport
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
_gov_violations = _meter.create_counter(
    "ariadne.governance.violations", description="Read-only governance violations per workup."
)
_eval_score = _meter.create_histogram(
    "ariadne.eval.score",
    unit="1",
    description="Eval accuracy/efficiency score per dimension (dimension in gen_ai.evaluation.name).",
)


@contextmanager
def workup_span(
    entity: str, dataset: str, *, semantic: bool = False, sql: bool = False
) -> Iterator[trace.Span]:
    """A GenAI ``invoke_agent`` span wrapping a workup; its duration is the task time."""
    # research(2026-06): gen_ai.* follows the OTel GenAI semantic conventions;
    # `gen_ai.agent.name` is in the experimental agents spec and may change in the
    # 1.0 stable semconv — revisit when it stabilizes.
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
    tradecraft: TradecraftReport | None = None,
    led: ProvenanceLedger,
    governance: GovernanceReport | None = None,
    profile: Profile | None = None,
) -> None:
    """Emit metrics + enrich the current span from the already-computed artifacts."""
    attrs = {"ariadne.dataset": dataset}
    n_calls = len(led.entries)
    fails = len(report.uncited) + len(report.dangling) + len(report.unsupported)
    _workups.add(1, attrs)
    _duration.record(duration_s, attrs)
    _evidence.add(n_calls, attrs)
    _failures.add(fails, attrs)
    span = trace.get_current_span()
    span.set_attribute("ariadne.evidence_calls", n_calls)
    span.set_attribute("ariadne.citation.ok", report.ok)
    span.set_attribute("ariadne.citation.uncited", len(report.uncited))
    span.set_attribute("ariadne.citation.unsupported", len(report.unsupported))
    if tradecraft is not None:
        span.set_attribute("ariadne.tradecraft.estimative_terms", len(tradecraft.standard_terms))
        span.set_attribute("ariadne.tradecraft.has_confidence", tradecraft.has_confidence_statement)
    if governance is not None:
        n_violations = len(governance.write_attempts)
        _gov_violations.add(n_violations, attrs)
        span.set_attribute("ariadne.governance.read_only_ok", governance.ok)
        span.set_attribute("ariadne.governance.write_attempts", n_violations)
    if profile is not None:
        span.set_attribute("ariadne.profile", profile.name)
        span.set_attribute("ariadne.profile.egress", profile.egress)


@contextmanager
def eval_span(entity: str, fixture: str) -> Iterator[trace.Span]:
    """A span wrapping a fixture scoring run; parents the gen_ai.evaluation.result events."""
    with _tracer.start_as_current_span(
        "evaluate",
        attributes={"ariadne.fixture": fixture, "ariadne.entity": entity},
    ) as span:
        yield span


def record_eval_metrics(report: EvalReport, *, fixture: str) -> None:
    """Emit accuracy as OTel telemetry from an already-computed needle report.

    # research(2026-06): OTel standardizes GenAI evaluation as a
    # `gen_ai.evaluation.result` event (`gen_ai.evaluation.name` + `.score.value` +
    # `.score.label`), not a metric instrument — so emit that event per dimension
    # AND an Ariadne-namespaced `ariadne.eval.score` histogram for dashboards,
    # mirroring this module's `gen_ai.*` attribute + `ariadne.*` metric split.
    """
    # (name, value, label) per dimension; a discrete label applies only to the
    # pass/fail `grounded` gate — continuous scores carry the value alone.
    dims: list[tuple[str, float, str | None]] = [
        ("grounded", float(report.grounded), "grounded" if report.grounded else "ungrounded"),
        ("recall", report.recall, None),
        ("trajectory", report.trajectory, None),
        ("pivot_burden", report.pivot_burden, None),
    ]
    if report.supporting_fact_f1 is not None:
        dims.append(("supporting_fact_f1", report.supporting_fact_f1, None))
    span = trace.get_current_span()
    for name, value, label in dims:
        _eval_score.record(value, {"gen_ai.evaluation.name": name, "ariadne.fixture": fixture})
        attrs: dict[str, str | float] = {
            "gen_ai.evaluation.name": name,
            "gen_ai.evaluation.score.value": value,
        }
        if label is not None:
            attrs["gen_ai.evaluation.score.label"] = label
        span.add_event("gen_ai.evaluation.result", attributes=attrs)


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
