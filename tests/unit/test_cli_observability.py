from __future__ import annotations

import ariadne.cli as cli


def test_main_calls_setup_telemetry(monkeypatch) -> None:
    called = {}
    monkeypatch.setattr("ariadne.cli.setup_telemetry", lambda: called.setdefault("yes", True))
    monkeypatch.setattr("ariadne.cli._run_eval", lambda *a, **k: 0)
    cli.main(["eval", "/tmp/nope", "--fixture", "halberd"])
    assert called.get("yes")
