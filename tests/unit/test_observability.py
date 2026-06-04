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
    exporter = InMemorySpanExporter()
    tp = TracerProvider()
    tp.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(tp)
    metrics.set_meter_provider(MeterProvider(metric_readers=[InMemoryMetricReader()]))
    pytest._otel_exporter = exporter  # type: ignore[attr-defined]  # ty:ignore[unresolved-attribute]
    yield


def _spans():
    return pytest._otel_exporter.get_finished_spans()  # type: ignore[attr-defined]  # ty:ignore[unresolved-attribute]


def test_workup_span_emits_invoke_agent_with_attributes() -> None:
    from ariadne.observability import workup_span

    pytest._otel_exporter.clear()  # type: ignore[attr-defined]  # ty:ignore[unresolved-attribute]
    with workup_span("Halberd", "synthetic", semantic=True):
        pass
    s = next(s for s in _spans() if s.name == "invoke_agent")
    assert s.attributes["gen_ai.agent.name"] == "ariadne"
    assert s.attributes["ariadne.dataset"] == "synthetic"
    assert s.attributes["ariadne.entity"] == "Halberd"


def test_record_workup_metrics_sets_span_attrs() -> None:
    from ariadne.observability import record_workup_metrics, workup_span
    from ariadne.provenance.citations import CitationReport
    from ariadne.provenance.ledger import ProvenanceLedger
    from ariadne.provenance.tradecraft import lint_estimative_language

    pytest._otel_exporter.clear()  # type: ignore[attr-defined]  # ty:ignore[unresolved-attribute]
    led = ProvenanceLedger()
    led.record("mcp__neo4j__read_neo4j_cypher", {"query": "Q"}, "ex")
    report = CitationReport(ok=False, cited=["g1"], dangling=[], unused=[], uncited=["x"])
    tc = lint_estimative_language("Halberd is likely the lead.")
    with workup_span("Halberd", "synthetic"):
        record_workup_metrics(
            entity="Halberd",
            dataset="synthetic",
            duration_s=1.5,
            report=report,
            tradecraft=tc,
            led=led,
        )
    s = next(s for s in _spans() if s.name == "invoke_agent")
    assert s.attributes["ariadne.evidence_calls"] == 1
    assert s.attributes["ariadne.citation.ok"] is False
    assert s.attributes["ariadne.citation.uncited"] == 1
    assert s.attributes["ariadne.citation.unsupported"] == 0


def test_record_workup_metrics_records_governance_violations() -> None:
    from ariadne.observability import record_workup_metrics, workup_span
    from ariadne.provenance.citations import CitationReport
    from ariadne.provenance.governance import audit_read_only
    from ariadne.provenance.ledger import ProvenanceLedger

    pytest._otel_exporter.clear()  # type: ignore[attr-defined]  # ty:ignore[unresolved-attribute]
    led = ProvenanceLedger()
    led.record("mcp__neo4j__read_neo4j_cypher", {"query": "CREATE (n) RETURN n"}, "ex")
    report = CitationReport(ok=True, cited=[], dangling=[], unused=[])
    governance = audit_read_only(led.entries)
    with workup_span("Halberd", "synthetic"):
        record_workup_metrics(
            entity="Halberd",
            dataset="synthetic",
            duration_s=1.0,
            report=report,
            tradecraft=None,
            led=led,
            governance=governance,
        )
    s = next(s for s in _spans() if s.name == "invoke_agent")
    assert s.attributes["ariadne.governance.read_only_ok"] is False
    assert s.attributes["ariadne.governance.write_attempts"] == 1


def test_setup_telemetry_is_noop_without_endpoint(monkeypatch) -> None:
    from ariadne import observability

    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    assert observability.setup_telemetry() is False
