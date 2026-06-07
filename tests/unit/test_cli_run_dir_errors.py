"""`ariadne report` / `eval` give an actionable error on a missing/incomplete run dir.

The dual-consumer error problem: a first-time user (or the agent driving the MCP) who typos
a path should get "what's wrong + how to fix", not a raw FileNotFoundError traceback.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ariadne.cli import _run_eval, _run_report

if TYPE_CHECKING:
    from pathlib import Path


def test_report_on_a_missing_dir_is_actionable(tmp_path: Path, capsys) -> None:
    rc = _run_report(str(tmp_path / "nope"))
    assert rc == 2
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "workup" in err  # tells the user how to fix it


def test_report_on_a_dir_without_a_note_is_actionable(tmp_path: Path, capsys) -> None:
    (tmp_path / "empty").mkdir()
    rc = _run_report(str(tmp_path / "empty"))
    assert rc == 2
    err = capsys.readouterr().err
    assert "note.md" in err
    assert "Traceback" not in err


def test_eval_on_a_missing_dir_is_actionable(tmp_path: Path, capsys) -> None:
    rc = _run_eval(str(tmp_path / "nope"))
    assert rc == 2
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "workup" in err
