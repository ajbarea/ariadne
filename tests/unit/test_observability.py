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
    reader = InMemoryMetricReader()
    metrics.set_meter_provider(MeterProvider(metric_readers=[reader]))
    pytest._otel_exporter = exporter  # type: ignore[attr-defined]  # ty:ignore[unresolved-attribute]
    pytest._otel_reader = reader  # type: ignore[attr-defined]  # ty:ignore[unresolved-attribute]
    yield


def _spans():
    return pytest._otel_exporter.get_finished_spans()  # type: ignore[attr-defined]  # ty:ignore[unresolved-attribute]


def _metric_points(name: str):
    """Data points for the named metric across the in-memory reader's collection."""
    data = pytest._otel_reader.get_metrics_data()  # type: ignore[attr-defined]  # ty:ignore[unresolved-attribute]
    points = []
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                if metric.name == name:
                    points.extend(metric.data.data_points)
    return points


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


def test_record_workup_metrics_records_profile() -> None:
    from ariadne.observability import record_workup_metrics, workup_span
    from ariadne.profiles import Envelope, Profile
    from ariadne.provenance.citations import CitationReport
    from ariadne.provenance.ledger import ProvenanceLedger

    pytest._otel_exporter.clear()  # type: ignore[attr-defined]  # ty:ignore[unresolved-attribute]
    led = ProvenanceLedger()
    report = CitationReport(ok=True, cited=[], dangling=[], unused=[])
    profile = Profile(
        name="fast-local",
        model="fast-local",
        egress="none",
        envelope=Envelope(max_turns=12, max_thinking_tokens=0),
    )
    with workup_span("Halberd", "synthetic"):
        record_workup_metrics(
            entity="Halberd",
            dataset="synthetic",
            duration_s=1.0,
            report=report,
            tradecraft=None,
            led=led,
            profile=profile,
        )
    s = next(s for s in _spans() if s.name == "invoke_agent")
    assert s.attributes["ariadne.profile"] == "fast-local"
    assert s.attributes["ariadne.profile.egress"] == "none"


def _needle_report(*, with_sf: bool = False):
    from ariadne.evaluation.needle import EvalReport

    return EvalReport(
        entity="Halberd",
        recall=1.0,
        trajectory=0.5,
        grounded=False,
        pivot_burden=2.0,
        queries_run=4,
        supporting_fact_f1=0.75 if with_sf else None,
        supporting_fact_precision=0.6 if with_sf else None,
        supporting_fact_recall=1.0 if with_sf else None,
    )


def test_eval_span_carries_fixture_and_entity() -> None:
    from ariadne.observability import eval_span

    pytest._otel_exporter.clear()  # type: ignore[attr-defined]  # ty:ignore[unresolved-attribute]
    with eval_span("Halberd", "halberd"):
        pass
    s = next(s for s in _spans() if s.name == "evaluate")
    assert s.attributes["ariadne.fixture"] == "halberd"
    assert s.attributes["ariadne.entity"] == "Halberd"


def test_record_eval_metrics_emits_evaluation_result_events() -> None:
    from ariadne.observability import eval_span, record_eval_metrics

    pytest._otel_exporter.clear()  # type: ignore[attr-defined]  # ty:ignore[unresolved-attribute]
    with eval_span("Halberd", "halberd"):
        record_eval_metrics(_needle_report(), fixture="halberd")
    s = next(s for s in _spans() if s.name == "evaluate")
    events = {
        e.attributes["gen_ai.evaluation.name"]: e
        for e in s.events
        if e.name == "gen_ai.evaluation.result"
    }
    # grounded + recall + trajectory + pivot_burden (no supporting_fact_f1 here)
    assert set(events) == {"grounded", "recall", "trajectory", "pivot_burden"}
    assert events["recall"].attributes["gen_ai.evaluation.score.value"] == 1.0
    assert events["grounded"].attributes["gen_ai.evaluation.score.value"] == 0.0
    assert events["grounded"].attributes["gen_ai.evaluation.score.label"] == "ungrounded"


def test_record_eval_metrics_includes_supporting_fact_f1_when_present() -> None:
    from ariadne.observability import eval_span, record_eval_metrics

    pytest._otel_exporter.clear()  # type: ignore[attr-defined]  # ty:ignore[unresolved-attribute]
    with eval_span("Halberd", "halberd"):
        record_eval_metrics(_needle_report(with_sf=True), fixture="halberd")
    s = next(s for s in _spans() if s.name == "evaluate")
    names = {
        e.attributes["gen_ai.evaluation.name"]
        for e in s.events
        if e.name == "gen_ai.evaluation.result"
    }
    assert "supporting_fact_f1" in names


def test_record_eval_metrics_records_score_histogram() -> None:
    from ariadne.observability import eval_span, record_eval_metrics

    with eval_span("Halberd", "halberd"):
        record_eval_metrics(_needle_report(), fixture="halberd")
    points = _metric_points("ariadne.eval.score")
    recorded = {p.attributes["gen_ai.evaluation.name"] for p in points}
    assert {"grounded", "recall", "trajectory", "pivot_burden"} <= recorded
    assert all(p.attributes["ariadne.fixture"] == "halberd" for p in points)


def test_setup_telemetry_is_noop_without_endpoint(monkeypatch) -> None:
    from ariadne import observability

    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    assert observability.setup_telemetry() is False
