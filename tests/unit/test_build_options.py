from __future__ import annotations

from ariadne.cli import build_options
from ariadne.graph.neo4j_server import GRAPH_TOOLS
from ariadne.provenance.ledger import ProvenanceLedger
from ariadne.relational.postgres_server import RELATIONAL_TOOLS


def test_graph_only_by_default() -> None:
    cfg = build_options(ledger=ProvenanceLedger(), env={})
    servers, hooks = cfg.mcp_servers, cfg.hooks
    assert isinstance(servers, dict) and isinstance(hooks, dict)
    assert set(servers) == {"neo4j"}
    assert cfg.allowed_tools == list(GRAPH_TOOLS)
    assert [m.matcher for m in hooks["PostToolUse"]] == ["mcp__neo4j__.*"]


def test_with_sql_adds_postgres_store_tools_and_hook() -> None:
    cfg = build_options(ledger=ProvenanceLedger(), env={}, with_sql=True)
    servers, hooks = cfg.mcp_servers, cfg.hooks
    assert isinstance(servers, dict) and isinstance(hooks, dict)
    assert set(servers) == {"neo4j", "postgres"}
    for tool in (*GRAPH_TOOLS, *RELATIONAL_TOOLS):
        assert tool in (cfg.allowed_tools or [])
    assert {m.matcher for m in hooks["PostToolUse"]} == {"mcp__neo4j__.*", "mcp__postgres__.*"}


def test_with_semantic_adds_the_ariadne_tool_and_server() -> None:
    from ariadne.cli import build_options
    from ariadne.provenance.ledger import ProvenanceLedger

    opts = build_options(
        ledger=ProvenanceLedger(), env={"DATABASE_URI": "postgresql://x"}, with_semantic=True
    )
    servers = opts.mcp_servers
    assert isinstance(servers, dict)
    assert "mcp__ariadne__hybrid_search" in opts.allowed_tools
    assert "ariadne" in set(servers)


def test_no_model_override_by_default() -> None:
    cfg = build_options(ledger=ProvenanceLedger(), env={})
    assert cfg.model is None  # SDK default / env applies -> zero regression


def test_model_and_envelope_set_when_given() -> None:
    cfg = build_options(
        ledger=ProvenanceLedger(), env={}, model="fast-local", max_turns=12, max_thinking_tokens=0
    )
    assert cfg.model == "fast-local"
    assert cfg.max_turns == 12
    assert cfg.max_thinking_tokens == 0  # 0 is a real value, not "omitted"


def test_no_skills_plugin_keeps_project_skill_default() -> None:
    cfg = build_options(ledger=ProvenanceLedger(), env={})
    assert cfg.skills == ["entity-workup"]  # default: the project .claude/skills/ skill
    assert not getattr(cfg, "plugins", None)
    assert cfg.setting_sources is None  # normal path: SDK defaults discovery to user+project


def test_skills_plugin_enables_the_staged_arm_in_isolation() -> None:
    # ratify (ADR-0034) toggles the candidate skill in/out by pointing the workup at a staged
    # plugin dir per arm. Two things must hold for the arm to be a clean measurement:
    #   * the staged plugin is the SOLE skill source — `setting_sources=[]` so no project/user
    #     skill leaks into the measured arm (the docs' "use the plugins option to load skills
    #     from a specific path");
    #   * the staged skills are ENABLED — `skills="all"`. The old `skills=[]` was an empty
    #     *allowlist* the SDK rejects every skill against, so the candidate could never fire and
    #     the SkillTester invocation gate would abstain on everything (ADR-0034 contract fix).
    cfg = build_options(ledger=ProvenanceLedger(), env={}, skills_plugin="/tmp/arm/candidate")
    assert cfg.plugins == [{"type": "local", "path": "/tmp/arm/candidate"}]
    assert cfg.skills == "all"
    assert cfg.setting_sources == []
