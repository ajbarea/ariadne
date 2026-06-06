"""Unit tests for ariadne.runs — run identity, paths, manifest, latest (ADR-0021)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ariadne.runs import (
    Manifest,
    build_workup_manifest,
    current_trace_hex,
    git_provenance,
    merge_scores,
    read_manifest,
    run_dir,
    run_id,
    scores_from_reports,
    slug,
    update_latest,
    write_manifest,
)


# --- slug ---
def test_slug_lowercases_and_replaces_nonalnum():
    assert slug("Halberd") == "halberd"
    assert slug("vince.kaminski@enron.com") == "vince-kaminski-enron-com"


def test_slug_empty_falls_back_to_entity():
    assert slug("!!!") == "entity"


# --- run identity ---
def test_run_id_uses_trace_prefix_when_present():
    now = datetime(2026, 6, 5, 18, 23, 1, tzinfo=UTC)
    rid = run_id(now, trace_hex="4bf92f3577b34da6a3ce929d0e0e4736")
    assert rid == "2026-06-05T18-23-01Z-4bf92f35"


def test_run_id_random_suffix_when_no_trace():
    now = datetime(2026, 6, 5, 18, 23, 1, tzinfo=UTC)
    a = run_id(now, trace_hex="")
    b = run_id(now, trace_hex="")
    assert a.startswith("2026-06-05T18-23-01Z-")
    assert len(a.rsplit("-", 1)[1]) == 8
    assert a != b  # random suffix disambiguates same-second runs


def test_current_trace_hex_empty_without_active_span():
    assert current_trace_hex() == ""


def test_run_dir_composes_dataset_slug_runid():
    now = datetime(2026, 6, 5, 18, 23, 1, tzinfo=UTC)
    d = run_dir("runs", "synthetic", "Halberd", now=now, trace_hex="4bf92f35aaaaaaaa")
    assert d == Path("runs/synthetic/halberd/2026-06-05T18-23-01Z-4bf92f35")


def test_run_dir_two_calls_never_collide():
    now = datetime(2026, 6, 5, 18, 23, 1, tzinfo=UTC)
    a = run_dir("runs", "synthetic", "Halberd", now=now)  # no trace -> random suffix
    b = run_dir("runs", "synthetic", "Halberd", now=now)
    assert a != b  # the no-overwrite property


# --- manifest: stubs mirroring the real report shapes ---
@dataclass
class _Cite:
    ok: bool = True
    dangling: list = field(default_factory=list)
    uncited: list = field(default_factory=list)
    unsupported: list = field(default_factory=list)


@dataclass
class _Trade:
    nonstandard_terms: list = field(default_factory=list)


@dataclass
class _Gov:
    ok: bool = True


def _manifest(**over) -> Manifest:
    base = {
        "run_id": "r",
        "entity": "Halberd",
        "dataset": "synthetic",
        "created_at": "t",
        "otel_trace_id": None,
        "ariadne_version": "0.1.0",
        "git_sha": "abc",
        "git_dirty": False,
        "model": None,
        "profile": "default",
        "params": {},
        "duration_s": 1.0,
        "exit_code": 0,
        "scores": {"eval": None},
    }
    base.update(over)
    return Manifest(**base)


def test_scores_from_reports_shapes_the_block():
    s = scores_from_reports(
        _Cite(ok=True, dangling=[], uncited=["x"], unsupported=[]),
        _Trade(nonstandard_terms=["likely"]),
        _Gov(ok=True),
    )
    assert s["citations"] == {"ok": True, "uncited": 1, "dangling": 0, "unsupported": 0}
    assert s["tradecraft"] == {"nonstandard_terms": ["likely"]}
    assert s["governance"] == {"ok": True}
    assert s["eval"] is None and s["rubric"] is None


def test_manifest_round_trips():
    m = _manifest(
        otel_trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
        model="claude-opus-4-8",
        params={"sql": True, "semantic": False, "entail": False, "strict": False},
        scores={"citations": {"ok": True}, "eval": None, "rubric": None},
    )
    assert Manifest.from_dict(m.to_dict()) == m


def test_write_then_read_manifest(tmp_path):
    write_manifest(tmp_path, _manifest())
    assert (tmp_path / "manifest.json").is_file()
    data = read_manifest(tmp_path)
    assert data is not None
    assert data["entity"] == "Halberd"


def test_read_manifest_absent_returns_none(tmp_path):
    assert read_manifest(tmp_path) is None


def test_merge_scores_updates_eval_without_touching_identity(tmp_path):
    write_manifest(tmp_path, _manifest(scores={"citations": {"ok": True}, "eval": None}))
    merge_scores(tmp_path, {"eval": {"grounded": True, "recall": 1.0, "trajectory": 0.8}})
    data = read_manifest(tmp_path)
    assert data is not None
    assert data["entity"] == "Halberd"  # identity untouched
    assert data["scores"]["eval"] == {"grounded": True, "recall": 1.0, "trajectory": 0.8}
    assert data["scores"]["citations"] == {"ok": True}  # existing block preserved


def test_merge_scores_absent_manifest_is_noop(tmp_path, capsys):
    merge_scores(tmp_path, {"eval": {"grounded": True}})  # must not raise
    assert not (tmp_path / "manifest.json").exists()
    assert "manifest" in capsys.readouterr().err.lower()


def test_git_provenance_returns_sha_and_dirty_flag():
    sha, dirty = git_provenance()
    assert isinstance(sha, str) and sha  # "unknown" or a short hash, never empty
    assert isinstance(dirty, bool)


def test_build_workup_manifest_assembles_record():
    m = build_workup_manifest(
        run_directory=Path("runs/synthetic/halberd/2026-06-05T18-23-01Z-4bf92f35"),
        entity="Halberd",
        dataset="synthetic",
        model="claude-opus-4-8",
        profile="default",
        params={"sql": True, "semantic": False, "entail": False, "strict": False},
        duration_s=42.7,
        exit_code=0,
        trace_hex="4bf92f3577b34da6a3ce929d0e0e4736",
        scores={"citations": {"ok": True}, "eval": None, "rubric": None},
    )
    assert m.run_id == "2026-06-05T18-23-01Z-4bf92f35"
    assert m.otel_trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert m.created_at.endswith("Z")


def test_update_latest_points_at_run(tmp_path):
    entity_dir = tmp_path / "synthetic" / "halberd"
    (entity_dir / "run-a").mkdir(parents=True)
    update_latest(entity_dir, "run-a")
    link = entity_dir / "latest"
    assert link.is_symlink()
    assert link.readlink() == Path("run-a")


def test_update_latest_replaces_existing(tmp_path):
    entity_dir = tmp_path / "synthetic" / "halberd"
    (entity_dir / "run-a").mkdir(parents=True)
    (entity_dir / "run-b").mkdir()
    update_latest(entity_dir, "run-a")
    update_latest(entity_dir, "run-b")
    assert (entity_dir / "latest").readlink() == Path("run-b")


def test_eval_score_block_shape(tmp_path):
    write_manifest(tmp_path, _manifest(scores={"eval": None, "rubric": None}))
    merge_scores(tmp_path, {"eval": {"grounded": True, "recall": 1.0, "trajectory": 0.83}})
    data = read_manifest(tmp_path)
    assert data is not None
    assert set(data["scores"]["eval"]) == {"grounded", "recall", "trajectory"}
