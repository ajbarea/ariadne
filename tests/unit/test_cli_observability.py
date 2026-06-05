from __future__ import annotations

import json

import ariadne.cli as cli


def test_main_calls_setup_telemetry(monkeypatch) -> None:
    called = {}
    monkeypatch.setattr("ariadne.cli.setup_telemetry", lambda: called.setdefault("yes", True))
    monkeypatch.setattr("ariadne.cli._run_eval", lambda *a, **k: 0)
    cli.main(["eval", "/tmp/nope", "--fixture", "halberd"])
    assert called.get("yes")


def test_run_eval_emits_eval_telemetry(tmp_path, monkeypatch) -> None:
    # _run_eval must surface accuracy as telemetry, not only print it.
    (tmp_path / "note.md").write_text("Halberd leads Signals-Cell [cite:g1].", encoding="utf-8")
    (tmp_path / "provenance.jsonl").write_text(
        json.dumps({"id": "g1", "tool_input": {"query": "MATCH (n) RETURN n"}}), encoding="utf-8"
    )
    captured = {}
    monkeypatch.setattr(
        "ariadne.cli.record_eval_metrics",
        lambda report, *, fixture: captured.update(fixture=fixture, entity=report.entity),
    )
    cli._run_eval(str(tmp_path), "halberd")
    assert captured["fixture"] == "halberd"
    assert captured["entity"] == "Halberd"


def test_run_eval_emits_reconciliation_telemetry(tmp_path, monkeypatch) -> None:
    # The --reconcile branch must surface reconciliation scores as telemetry too.
    (tmp_path / "note.md").write_text(
        "Halberd and Wren are both at Compound-Alpha; the personnel records "
        "corroborate this, consistent across both stores.",
        encoding="utf-8",
    )
    (tmp_path / "provenance.jsonl").write_text(
        json.dumps({"id": "g1", "tool_input": {"query": "MATCH (n) RETURN n"}}), encoding="utf-8"
    )
    captured = {}
    monkeypatch.setattr(
        "ariadne.cli.record_reconciliation_metrics",
        lambda report, *, fixture: captured.update(fixture=fixture),
    )
    cli._run_eval(str(tmp_path), "halberd", reconcile="synthetic")
    assert captured["fixture"] == "synthetic"
