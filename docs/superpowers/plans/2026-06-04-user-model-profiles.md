# User-Selectable Model Profiles — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user pick which model (and its operating envelope) runs a workup, from a curated operator-defined allowlist, without forking the analytic logic or breaking the air-gap governance posture.

**Architecture:** A pure, Ariadne-owned profile registry (`src/ariadne/profiles.py`) maps a profile name → `{model, egress, description, envelope}`. `run_workup` resolves the profile once and threads `model` + envelope (`max_turns`, `max_thinking_tokens`) into `ClaudeAgentOptions` via `build_options`. The built-in `default` profile sets no model (byte-identical to today). Surfaces: CLI `--profile` + `ariadne profiles`, MCP `workup(profile=)` + `list_profiles()`, plugin SKILL.md. The profile + egress are recorded in `governance.json` and on the OTel span.

**Tech Stack:** Python 3.14, `tomllib` (stdlib), `claude-agent-sdk` (`ClaudeAgentOptions` exposes `model`, `max_turns`, `max_thinking_tokens` — verified 2026-06-04), `uv` + `ruff` + `ty` + `pytest`. Spec: `docs/superpowers/specs/2026-06-04-user-model-selection-design.md`.

---

## File Structure

- **Create** `src/ariadne/profiles.py` — `Envelope`, `Profile`, `DEFAULT_PROFILE`, `load_profiles(env)`, `resolve_profile(name, registry)`. Pure; no I/O beyond reading the TOML named by `ARIADNE_PROFILES`.
- **Create** `tests/unit/test_profiles.py` — hermetic resolver/loader tests.
- **Create** `infra/profiles.example.toml` — operator example.
- **Create** `docs/architecture/decisions/0013-user-selectable-model-profiles.md` — ADR.
- **Modify** `src/ariadne/cli.py` — `build_options` (model + envelope params), `run_workup` (`profile=`), `parse_args` (`--profile` + `profiles` subcommand), `main` (dispatch), `_run_profiles`.
- **Modify** `src/ariadne/report/note.py` — `write_outputs(profile=)` → merge into `governance.json`.
- **Modify** `src/ariadne/observability.py` — `record_workup_metrics(profile=)` → span attrs.
- **Modify** `src/ariadne/mcp_server.py` — `workup(profile=)`, `run_workup_tool(profile=)`, new `list_profiles()` tool.
- **Modify** `infra/litellm/config.yaml` — named routes matching profile model ids (D5).
- **Modify** `plugins/ariadne/skills/analyst-workup/SKILL.md` — document the `profile` argument.

> **Coordination note:** another agent is reworking the Zensical docs site. Do **not** edit `zensical.toml` or `docs/style.css`. The new ADR-0013 file needs a nav entry — leave that to the site agent (flag it).

---

## Task 1: Profile registry module

**Files:**
- Create: `src/ariadne/profiles.py`
- Test: `tests/unit/test_profiles.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_profiles.py
from __future__ import annotations

import pytest

from ariadne.profiles import load_profiles, resolve_profile


def test_default_only_when_no_env() -> None:
    reg = load_profiles({})
    assert set(reg) == {"default"}
    assert reg["default"].model is None  # zero-regression: no model override


def test_resolve_unknown_lists_valid_names() -> None:
    reg = load_profiles({})
    with pytest.raises(ValueError, match="Valid profiles: default"):
        resolve_profile("bogus", reg)


def test_toml_override_adds_profile_with_envelope(tmp_path) -> None:
    p = tmp_path / "profiles.toml"
    p.write_text(
        '[profiles.fast-local]\n'
        'model = "fast-local"\n'
        'egress = "none"\n'
        'description = "Local qwen via Ollama"\n'
        '[profiles.fast-local.envelope]\n'
        'max_turns = 12\n'
        'max_thinking_tokens = 0\n',
        encoding="utf-8",
    )
    reg = load_profiles({"ARIADNE_PROFILES": str(p)})
    assert set(reg) == {"default", "fast-local"}
    fl = resolve_profile("fast-local", reg)
    assert fl.model == "fast-local"
    assert fl.egress == "none"
    assert fl.envelope.max_turns == 12
    assert fl.envelope.max_thinking_tokens == 0


def test_air_gap_registry_makes_cloud_unavailable(tmp_path) -> None:
    p = tmp_path / "profiles.toml"
    p.write_text('[profiles.air-gap]\nmodel = "qwen3:30b"\negress = "none"\n', encoding="utf-8")
    reg = load_profiles({"ARIADNE_PROFILES": str(p)})
    with pytest.raises(ValueError):
        resolve_profile("rigorous", reg)  # no cloud profile defined -> not selectable
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -m pytest tests/unit/test_profiles.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ariadne.profiles'`

- [ ] **Step 3: Implement the module**

```python
# src/ariadne/profiles.py
"""Curated model profiles (ADR-0013).

A user selects a profile by name; the operator curates the allowlist. A profile
binds a model to an operating envelope. Air-gap deployments omit cloud profiles, so
an analyst cannot select one — an unknown name is rejected with the valid names.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Envelope:
    """Per-model loop discipline (spec D6). ``None`` = use the SDK default."""

    max_turns: int | None = None
    max_thinking_tokens: int | None = None


@dataclass(frozen=True)
class Profile:
    name: str
    model: str | None = None  # None = deployment default (ANTHROPIC_* env)
    egress: str = "unknown"  # advisory governance class, surfaced for audit
    description: str = ""
    envelope: Envelope = field(default_factory=Envelope)


DEFAULT_PROFILE = Profile(
    name="default",
    egress="inherit",
    description="Use the deployment's configured model (ANTHROPIC_* env).",
)


def load_profiles(env: Mapping[str, str]) -> dict[str, Profile]:
    """Built-in ``default`` plus operator profiles from the ``ARIADNE_PROFILES`` TOML."""
    registry: dict[str, Profile] = {"default": DEFAULT_PROFILE}
    path = env.get("ARIADNE_PROFILES")
    if not path:
        return registry
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    for name, spec in data.get("profiles", {}).items():
        env_spec = spec.get("envelope", {})
        registry[name] = Profile(
            name=name,
            model=spec.get("model"),
            egress=spec.get("egress", "unknown"),
            description=spec.get("description", ""),
            envelope=Envelope(
                max_turns=env_spec.get("max_turns"),
                max_thinking_tokens=env_spec.get("max_thinking_tokens"),
            ),
        )
    return registry


def resolve_profile(name: str, registry: Mapping[str, Profile]) -> Profile:
    """Look up a profile; unknown name -> ``ValueError`` enumerating valid names."""
    try:
        return registry[name]
    except KeyError:
        valid = ", ".join(sorted(registry))
        raise ValueError(f"Unknown profile {name!r}. Valid profiles: {valid}") from None
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run python -m pytest tests/unit/test_profiles.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/ariadne/profiles.py tests/unit/test_profiles.py
git commit -m "feat(profiles): curated model-profile registry + resolver"
```

---

## Task 2: Thread model + envelope through `build_options`

**Files:**
- Modify: `src/ariadne/cli.py` (`build_options`, line ~196; `Any` import line 16)
- Test: `tests/unit/test_build_options.py`

- [ ] **Step 1: Add the failing tests** (append to `tests/unit/test_build_options.py`)

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -m pytest tests/unit/test_build_options.py -q`
Expected: FAIL — `TypeError: build_options() got an unexpected keyword argument 'model'`

- [ ] **Step 3: Implement** — change the import on line 16 of `src/ariadne/cli.py`:

```python
from typing import TYPE_CHECKING, Any
```

Then change the `build_options` signature and its `return` (lines ~196-226):

```python
def build_options(
    *,
    ledger: ProvenanceLedger,
    env: dict[str, str],
    with_sql: bool = False,
    with_semantic: bool = False,
    model: str | None = None,
    max_turns: int | None = None,
    max_thinking_tokens: int | None = None,
) -> ClaudeAgentOptions:
    hook = make_provenance_hook(ledger)
    mcp_servers: dict[str, McpServerConfig] = {"neo4j": neo4j_stdio_config(env)}
    allowed_tools = list(GRAPH_TOOLS)
    matchers = [HookMatcher(matcher="mcp__neo4j__.*", hooks=[hook])]
    if with_sql:
        mcp_servers["postgres"] = postgres_stdio_config(env)
        allowed_tools += list(RELATIONAL_TOOLS)
        matchers.append(HookMatcher(matcher="mcp__postgres__.*", hooks=[hook]))
    if with_semantic:
        from ariadne.unstructured.embed import SentenceTransformerEmbedder
        from ariadne.unstructured.search_tool import ARIADNE_TOOLS, make_ariadne_server

        embedder = SentenceTransformerEmbedder()
        mcp_servers["ariadne"] = make_ariadne_server(env, embedder)
        allowed_tools += list(ARIADNE_TOOLS)
        matchers.append(HookMatcher(matcher="mcp__ariadne__.*", hooks=[hook]))
    # Envelope/model are optional: omit unset fields so the SDK default applies.
    extra: dict[str, Any] = {}
    if model is not None:
        extra["model"] = model
    if max_turns is not None:
        extra["max_turns"] = max_turns
    if max_thinking_tokens is not None:
        extra["max_thinking_tokens"] = max_thinking_tokens
    return ClaudeAgentOptions(
        mcp_servers=mcp_servers,
        allowed_tools=allowed_tools,
        system_prompt=_SYSTEM_PROMPT,
        permission_mode="default",
        skills=["entity-workup"],  # SDK auto-allows Skill tool and sets setting_sources
        hooks={"PostToolUse": matchers},
        **extra,
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run python -m pytest tests/unit/test_build_options.py -q`
Expected: PASS (5 passed — the 3 originals plus the 2 new)

- [ ] **Step 5: Commit**

```bash
git add src/ariadne/cli.py tests/unit/test_build_options.py
git commit -m "feat(profiles): build_options accepts model + envelope (omitted when unset)"
```

---

## Task 3: Resolve the profile in `run_workup` + surface it in governance/telemetry

**Files:**
- Modify: `src/ariadne/cli.py` (`run_workup`, line ~229)
- Modify: `src/ariadne/report/note.py` (`write_outputs`)
- Modify: `src/ariadne/observability.py` (`record_workup_metrics`)
- Test: `tests/unit/test_note_outputs.py`, `tests/unit/test_observability.py`

- [ ] **Step 1: Add the failing tests**

In `tests/unit/test_note_outputs.py` add:

```python
def test_governance_json_records_profile(tmp_path) -> None:
    import json

    from ariadne.profiles import Envelope, Profile
    from ariadne.provenance.governance import audit_read_only
    from ariadne.provenance.ledger import ProvenanceLedger
    from ariadne.provenance.citations import validate_citations
    from ariadne.report.note import write_outputs

    ledger = ProvenanceLedger()
    gov = audit_read_only(ledger.entries)
    report = validate_citations("", ledger)
    prof = Profile(name="fast-local", model="fast-local", egress="none",
                   envelope=Envelope(max_turns=12, max_thinking_tokens=0))
    write_outputs(tmp_path, entity="X", note="", ledger=ledger, report=report,
                  governance=gov, profile=prof)
    payload = json.loads((tmp_path / "governance.json").read_text())
    assert payload["profile"]["name"] == "fast-local"
    assert payload["profile"]["egress"] == "none"
    assert payload["profile"]["max_turns"] == 12
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -m pytest tests/unit/test_note_outputs.py::test_governance_json_records_profile -q`
Expected: FAIL — `TypeError: write_outputs() got an unexpected keyword argument 'profile'`

- [ ] **Step 3: Implement `write_outputs`** — in `src/ariadne/report/note.py`, add the import (matching the file's `# noqa: TC001` style) after line 12:

```python
from ariadne.profiles import Profile  # noqa: TC001
```

Change the signature (line ~15) to add `profile`:

```python
def write_outputs(
    out_dir: str | Path,
    *,
    entity: str,
    note: str,
    ledger: ProvenanceLedger,
    report: CitationReport,
    tradecraft: TradecraftReport | None = None,
    governance: GovernanceReport | None = None,
    profile: Profile | None = None,
) -> None:
```

Replace the `if governance is not None:` block (lines ~37-40) with:

```python
    if governance is not None:
        payload = asdict(governance)
        if profile is not None:
            payload["profile"] = {
                "name": profile.name,
                "egress": profile.egress,
                "max_turns": profile.envelope.max_turns,
                "max_thinking_tokens": profile.envelope.max_thinking_tokens,
            }
        (out_dir / "governance.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Implement `record_workup_metrics`** — in `src/ariadne/observability.py`, add a TYPE_CHECKING import near the top (with the other artifact imports) :

```python
from ariadne.profiles import Profile  # noqa: TC001
```

Add `profile` to the signature (line ~69) and a span block (after the governance block, ~line 99):

```python
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
```

```python
    if profile is not None:
        span.set_attribute("ariadne.profile", profile.name)
        span.set_attribute("ariadne.profile.egress", profile.egress)
```

- [ ] **Step 5: Implement `run_workup`** — in `src/ariadne/cli.py`, add `profile` to the signature (line ~229) and resolve it:

```python
async def run_workup(
    entity: str,
    out_root: str,
    env: dict[str, str],
    *,
    with_sql: bool = False,
    with_semantic: bool = False,
    with_entail: bool = False,
    dataset: str = "synthetic",
    profile: str = "default",
) -> int:
    from ariadne.datasets.base import get_adapter
    from ariadne.profiles import load_profiles, resolve_profile

    get_adapter(dataset)  # raises KeyError on unknown; synthetic uses the seeded graph
    prof = resolve_profile(profile, load_profiles(env))
    ledger = ProvenanceLedger()
    options = build_options(
        ledger=ledger,
        env=env,
        with_sql=with_sql,
        with_semantic=with_semantic,
        model=prof.model,
        max_turns=prof.envelope.max_turns,
        max_thinking_tokens=prof.envelope.max_thinking_tokens,
    )
```

Then pass `profile=prof` to the existing `record_workup_metrics(...)` and `write_outputs(...)` calls (lines ~269 and ~279).

- [ ] **Step 6: Run to verify pass**

Run: `uv run python -m pytest tests/unit/test_note_outputs.py tests/unit/test_observability.py tests/unit/test_build_options.py -q`
Expected: PASS (all)

- [ ] **Step 7: Commit**

```bash
git add src/ariadne/cli.py src/ariadne/report/note.py src/ariadne/observability.py tests/unit/test_note_outputs.py
git commit -m "feat(profiles): resolve profile in run_workup; record profile+egress in governance.json + OTel"
```

---

## Task 4: CLI — `--profile` flag and `ariadne profiles` command

**Files:**
- Modify: `src/ariadne/cli.py` (`parse_args` ~54, `main` ~321, new `_run_profiles`)
- Test: `tests/unit/test_cli_args.py`

- [ ] **Step 1: Add the failing tests** (append to `tests/unit/test_cli_args.py`)

```python
def test_workup_accepts_profile_flag() -> None:
    from ariadne.cli import parse_args

    args = parse_args(["workup", "Halberd", "--profile", "fast-local"])
    assert args.profile == "fast-local"


def test_workup_profile_defaults_to_default() -> None:
    from ariadne.cli import parse_args

    args = parse_args(["workup", "Halberd"])
    assert args.profile == "default"


def test_profiles_subcommand_parses() -> None:
    from ariadne.cli import parse_args

    args = parse_args(["profiles"])
    assert args.command == "profiles"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -m pytest tests/unit/test_cli_args.py -q`
Expected: FAIL — `AttributeError: 'Namespace' object has no attribute 'profile'`

- [ ] **Step 3: Implement** — in `parse_args`, add to the `workup` parser (after the `--entail` argument, ~line 82):

```python
    wk.add_argument(
        "--profile",
        default="default",
        help="Model profile from the curated allowlist (see `ariadne profiles`).",
    )
```

Add a `profiles` subparser (after the `rubric`/`index` subparsers, before `return parser.parse_args(argv)`):

```python
    sub.add_parser("profiles", help="List the available model profiles (no API key needed)")
```

Add `_run_profiles` (near `_run_rubric`):

```python
def _run_profiles(env: dict[str, str]) -> int:
    """List the curated model profiles this deployment offers."""
    from ariadne.profiles import load_profiles

    for name, p in sorted(load_profiles(env).items()):
        model = p.model or "(deployment default)"
        print(f"{name:<14} egress={p.egress:<9} model={model}")
        if p.description:
            print(f"{'':<14} {p.description}")
    return 0
```

In `main`, dispatch `profiles` alongside the other no-API-key commands (next to the `eval`/`index` checks, ~line 328):

```python
    if args.command == "profiles":
        return _run_profiles(dict(os.environ))
```

And add `profile=args.profile` to the `run_workup(...)` call at the bottom of `main` (~line 340):

```python
    return asyncio.run(
        run_workup(
            args.entity,
            args.out,
            dict(os.environ),
            with_sql=args.sql,
            with_semantic=args.semantic,
            with_entail=args.entail,
            dataset=args.dataset,
            profile=args.profile,
        )
    )
```

> Note: confirm the exact existing keyword args in the `run_workup(...)` call before editing; add only `profile=args.profile`, leave the rest unchanged.

- [ ] **Step 4: Run to verify pass**

Run: `uv run python -m pytest tests/unit/test_cli_args.py -q`
Expected: PASS

- [ ] **Step 5: Verify the listing renders**

Run: `uv run ariadne profiles`
Expected: prints a `default` line with `model=(deployment default)`.

- [ ] **Step 6: Commit**

```bash
git add src/ariadne/cli.py tests/unit/test_cli_args.py
git commit -m "feat(profiles): ariadne workup --profile + ariadne profiles listing"
```

---

## Task 5: MCP — `workup(profile=)` and `list_profiles()` tool

**Files:**
- Modify: `src/ariadne/mcp_server.py` (`run_workup_tool` ~37, `workup` ~70, new `list_profiles`)
- Test: `tests/unit/test_mcp_server.py`

- [ ] **Step 1: Add the failing tests** (append to `tests/unit/test_mcp_server.py`)

```python
def test_run_workup_tool_forwards_profile() -> None:
    import asyncio

    from ariadne.mcp_server import run_workup_tool

    seen: dict[str, object] = {}

    async def fake_runner(entity, out_root, env, **kwargs) -> int:
        seen.update(kwargs)
        (__import__("pathlib").Path(out_root) / "x" / "note.md").parent.mkdir(parents=True)
        (__import__("pathlib").Path(out_root) / "x" / "note.md").write_text("ok")
        return 0

    asyncio.run(
        run_workup_tool("E", profile="fast-local", runner=fake_runner, out_root="/tmp/awt", slug="x")
    )
    assert seen["profile"] == "fast-local"


def test_list_profiles_returns_default() -> None:
    import asyncio

    from ariadne.mcp_server import list_profiles

    out = asyncio.run(list_profiles())
    assert "default" in out
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -m pytest tests/unit/test_mcp_server.py -q`
Expected: FAIL — `TypeError: run_workup_tool() got an unexpected keyword argument 'profile'` (and `ImportError` for `list_profiles`)

- [ ] **Step 3: Implement** — in `src/ariadne/mcp_server.py`, add `profile` to `run_workup_tool` signature (~line 37) and forward it to the runner:

```python
async def run_workup_tool(
    entity: str,
    *,
    dataset: str = "synthetic",
    sql: bool = False,
    semantic: bool = False,
    profile: str = "default",
    env: dict[str, str] | None = None,
    runner: _Runner | None = None,
    out_root: str | None = None,
    slug: str | None = None,
) -> str:
```

In its body, add `profile=profile` to the `await runner(...)` call:

```python
        await runner(
            entity,
            out_root,
            base_env,
            with_sql=sql,
            dataset=dataset,
            with_semantic=semantic,
            profile=profile,
        )
```

Update the `workup` tool (~line 70):

```python
@mcp.tool()
async def workup(
    entity: str,
    dataset: str = "synthetic",
    sql: bool = False,
    semantic: bool = False,
    profile: str = "default",
) -> str:
    """Produce a rigorous, citation-grounded analytic note for a target entity.

    Traverses the graph + (optionally) relational and semantic stores, reconciles
    across sources, and returns a note where every fact carries a [cite:gN] source.
    ``profile`` selects the model + operating envelope from the deployment's
    curated allowlist (see ``list_profiles``).
    """
    return await run_workup_tool(
        entity, dataset=dataset, sql=sql, semantic=semantic, profile=profile
    )


@mcp.tool()
async def list_profiles() -> dict[str, Any]:
    """List the model profiles this deployment offers (the curated allowlist)."""
    from ariadne.profiles import load_profiles

    return {
        name: {"model": p.model, "egress": p.egress, "description": p.description}
        for name, p in load_profiles(dict(os.environ)).items()
    }
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run python -m pytest tests/unit/test_mcp_server.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ariadne/mcp_server.py tests/unit/test_mcp_server.py
git commit -m "feat(profiles): MCP workup(profile=) + list_profiles tool"
```

---

## Task 6: Operator config, LiteLLM routes, plugin docs

**Files:**
- Create: `infra/profiles.example.toml`
- Modify: `infra/litellm/config.yaml`
- Modify: `plugins/ariadne/skills/analyst-workup/SKILL.md`

- [ ] **Step 1: Create `infra/profiles.example.toml`**

```toml
# Operator-curated model profiles (ADR-0013). Copy this file and point
# ARIADNE_PROFILES at it. Air-gap deployments: define ONLY local profiles — an
# analyst then cannot select a cloud model, because an unknown name is rejected.

[profiles.default]
# model omitted -> use the deployment's ANTHROPIC_* env (zero behaviour change)
egress = "inherit"
description = "Deployment default model."

[profiles.fast-local]
model = "fast-local"   # a LiteLLM model_name routing to a local Ollama worker
egress = "none"
description = "Local open-weight model via Ollama; lean envelope."
[profiles.fast-local.envelope]
max_turns = 16
max_thinking_tokens = 0   # thinking off (also set serving-side) keeps the loop cheap

[profiles.rigorous]
model = "claude-opus-4-8"
egress = "anthropic"
description = "Frontier Claude for the hardest analytic products."

[profiles.air-gap]
model = "air-gap"      # a LiteLLM route to an in-enclave open-weight worker
egress = "none"
description = "In-enclave open-weight model; no outbound network."
[profiles.air-gap.envelope]
max_turns = 16
max_thinking_tokens = 0
```

- [ ] **Step 2: Add named routes to `infra/litellm/config.yaml`** — add these entries to `model_list` *above* the existing `model_name: "*"` wildcard (the wildcard stays as the catch-all):

```yaml
  # Named routes matching the profile `model` ids in infra/profiles.example.toml.
  - model_name: fast-local
    litellm_params:
      model: ollama_chat/qwen3:14b
      api_base: http://localhost:11434
      num_ctx: 32768
  - model_name: air-gap
    litellm_params:
      model: ollama_chat/qwen3:30b
      api_base: http://localhost:11434
      num_ctx: 32768
  # In a HYBRID deployment, add a `rigorous` route here that passes through to
  # Anthropic (model: anthropic/claude-opus-4-8 + api_key). Omit it in an air-gap
  # deployment so the `rigorous` profile simply has no backing route.
```

- [ ] **Step 3: Document the profile arg in the plugin skill** — first read `plugins/ariadne/skills/analyst-workup/SKILL.md`, then add one line to the tool-usage section noting that `workup` accepts a `profile` argument (model + envelope from the curated allowlist) and that `list_profiles` returns the available names. Match the file's existing voice; do not restructure it.

- [ ] **Step 4: Verify the example TOML loads**

Run: `uv run python -c "from ariadne.profiles import load_profiles; r = load_profiles({'ARIADNE_PROFILES': 'infra/profiles.example.toml'}); print(sorted(r)); print(r['fast-local'].envelope)"`
Expected: `['air-gap', 'default', 'fast-local', 'rigorous']` and `Envelope(max_turns=16, max_thinking_tokens=0)`

- [ ] **Step 5: Commit**

```bash
git add infra/profiles.example.toml infra/litellm/config.yaml plugins/ariadne/skills/analyst-workup/SKILL.md
git commit -m "feat(profiles): operator example TOML, LiteLLM named routes, plugin doc"
```

---

## Task 7: ADR-0013

**Files:**
- Create: `docs/architecture/decisions/0013-user-selectable-model-profiles.md`

- [ ] **Step 1: Write the ADR** (MADR format, matching ADR-0012's structure)

```markdown
# 0013 — User-selectable model profiles

- **Status:** Accepted (2026-06-04)
- **Deciders:** Ariadne maintainers
- **Relates to:** [ADR-0012](0012-cloud-vs-air-gapped-deployment-fork.md) (the single-seam model fork this exposes to users)

## Context

Model selection was deployment-env-only (`ANTHROPIC_BASE_URL` + `ANTHROPIC_MODEL` +
the LiteLLM config). Users could not pick a model per workup. Naively adding a
free-form `model` parameter would break the ADR-0012 air-gap posture — an analyst
could point a workup at a cloud model from inside an enclave.

A live open-weight run (2026-06-04) also showed that a small local model needs a
*leaner loop* than a frontier model (it was throughput-bound on a large, growing
context), so model selection must carry an operating envelope, not just a name.

## Decision

Expose a **curated profile allowlist**, Ariadne-owned. A profile binds
`{model, egress, description, envelope}` where the envelope is `{max_turns,
max_thinking_tokens}`. The built-in `default` profile sets no model (zero
regression). Operators extend the allowlist via an `ARIADNE_PROFILES` TOML; air-gap
deployments define only local profiles, so a cloud selection is impossible by
construction (an unknown name is rejected with the valid names). The profile + egress
are recorded in `governance.json` and on the OTel span for audit.

`tool_result_cap` was considered for the envelope and **rejected for v1**: the
context bulk is external `mcp__neo4j__`/`mcp__postgres__` results, the PostToolUse
hook only observes (cannot rewrite a result), and those servers carry their own
guardrails — so a uniform cap is not cleanly available and would not have helped the
measured case. Serving-side thinking-off is the larger practical win and is config.

## Consequences

- Users get real choice within vetted options; governance is preserved by curation,
  not by runtime network enforcement (which remains the separate ADR-0012 follow-up).
- A profile is `model + envelope`, so a local profile runs lean and a frontier
  profile runs generous from one codebase — no fork in the analytic logic.
- The allowlist is Ariadne-side (not derived from LiteLLM), so it works for direct
  Anthropic, LiteLLM→Ollama, vLLM, or OpenRouter backends alike.
```

- [ ] **Step 2: Commit** (nav entry deferred to the site agent)

```bash
git add docs/architecture/decisions/0013-user-selectable-model-profiles.md
git commit -m "docs(adr): 0013 user-selectable model profiles"
```

---

## Task 8: Final verification

- [ ] **Step 1: Full hermetic suite**

Run: `uv run python -m pytest tests/unit tests/test_smoke.py -q`
Expected: PASS (186 prior + the new tests).

- [ ] **Step 2: Lint (whole-repo, both with and without optional extras — the standing trap)**

Run:
```bash
uv sync --group dev && make lint
uv sync --group dev --extra rubric --extra eval --extra embed --extra otel && make lint
```
Expected: `All checks passed!` both times. (The feature adds no optional-extra imports — `tomllib` is stdlib — so both should be clean; run both anyway.)

- [ ] **Step 3: Smoke the no-API-key surfaces**

Run:
```bash
uv run ariadne profiles
ARIADNE_PROFILES=infra/profiles.example.toml uv run ariadne profiles
```
Expected: first prints just `default`; second prints `air-gap`, `default`, `fast-local`, `rigorous`.

- [ ] **Step 4: Confirm zero regression on the default path**

Run: `uv run python -c "from ariadne.cli import build_options; from ariadne.provenance.ledger import ProvenanceLedger; print(build_options(ledger=ProvenanceLedger(), env={}).model)"`
Expected: `None` (no model override when no profile is chosen).

---

## Self-Review

**Spec coverage:**
- D1 registry/resolver/TOML/default → Task 1 ✅
- D2 build_options + run_workup threading → Tasks 2, 3 ✅
- D3 CLI `--profile` + `profiles`; MCP `workup(profile=)` + `list_profiles`; plugin SKILL.md → Tasks 4, 5, 6 ✅
- D4 governance.json + OTel surfacing → Task 3 ✅
- D5 LiteLLM named routes → Task 6 ✅
- D6 envelope (`max_turns`, `max_thinking_tokens`) → Tasks 1, 2, 3 ✅; `tool_result_cap` explicitly out of scope (spec non-goal) ✅
- ADR-0013 → Task 7 ✅

**Type consistency:** `Profile{name, model, egress, description, envelope}`, `Envelope{max_turns, max_thinking_tokens}`, `load_profiles(env)`, `resolve_profile(name, registry)` — used identically across Tasks 1-7. `build_options(..., model, max_turns, max_thinking_tokens)` matches `run_workup`'s call. `write_outputs(..., profile=Profile)` and `record_workup_metrics(..., profile=Profile)` match `run_workup`'s `prof` object.

**Placeholder scan:** none — every code step is complete; the only prose step (plugin SKILL.md, Task 6 Step 3) points at reading the file first because its content must match an existing voice.
