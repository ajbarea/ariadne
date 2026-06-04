from __future__ import annotations

import asyncio
from pathlib import Path

from ariadne.mcp_server import mcp, run_workup_tool


def test_server_is_named_ariadne() -> None:
    assert mcp.name == "ariadne"


def test_run_workup_tool_returns_the_note(tmp_path) -> None:
    async def fake_runner(
        entity, out_root, env, *, with_sql, dataset, with_semantic, profile="default"
    ):
        d = Path(out_root) / "halberd"
        d.mkdir(parents=True, exist_ok=True)
        (d / "note.md").write_text("# Workup\nHalberd is co-located at Compound-Alpha [cite:g1].")
        return 0

    note = asyncio.run(
        run_workup_tool(
            "Halberd",
            dataset="synthetic",
            sql=False,
            semantic=False,
            env={},
            runner=fake_runner,
            out_root=str(tmp_path),
            slug="halberd",
        )
    )
    assert "Compound-Alpha" in note and "[cite:g1]" in note


def test_run_workup_tool_reports_when_no_note(tmp_path) -> None:
    async def fake_runner(
        entity, out_root, env, *, with_sql, dataset, with_semantic, profile="default"
    ):
        return 1

    note = asyncio.run(
        run_workup_tool(
            "Nobody",
            env={},
            runner=fake_runner,
            out_root=str(tmp_path),
            slug="nobody",
        )
    )
    assert "no analytic note" in note.lower()


def test_run_workup_tool_cleans_up_its_temp_dir() -> None:
    seen: dict[str, str] = {}

    async def fake_runner(
        entity, out_root, env, *, with_sql, dataset, with_semantic, profile="default"
    ):
        seen["out_root"] = out_root
        d = Path(out_root) / "x"
        d.mkdir(parents=True, exist_ok=True)
        (d / "note.md").write_text("n")
        return 0

    # No out_root passed -> run_workup_tool creates a tempdir and must remove it.
    note = asyncio.run(run_workup_tool("x", env={}, runner=fake_runner, slug="x"))
    assert note == "n"
    assert not Path(seen["out_root"]).exists()  # cleaned up


def test_run_workup_tool_forwards_profile(tmp_path) -> None:
    from ariadne.mcp_server import run_workup_tool

    seen: dict[str, object] = {}

    async def fake_runner(entity, out_root, env, **kwargs) -> int:
        seen.update(kwargs)
        d = Path(out_root) / "x"
        d.mkdir(parents=True, exist_ok=True)
        (d / "note.md").write_text("ok")
        return 0

    asyncio.run(
        run_workup_tool(
            "E", profile="fast-local", runner=fake_runner, out_root=str(tmp_path), slug="x"
        )
    )
    assert seen["profile"] == "fast-local"


def test_list_profiles_returns_default() -> None:
    from ariadne.mcp_server import list_profiles

    out = asyncio.run(list_profiles())
    assert "default" in out
