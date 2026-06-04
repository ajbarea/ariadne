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
        "[profiles.fast-local]\n"
        'model = "fast-local"\n'
        'egress = "none"\n'
        'description = "Local qwen via Ollama"\n'
        "[profiles.fast-local.envelope]\n"
        "max_turns = 12\n"
        "max_thinking_tokens = 0\n",
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
    with pytest.raises(ValueError, match="Valid profiles"):
        resolve_profile("rigorous", reg)  # no cloud profile defined -> not selectable


def test_strict_parse_rejects_unknown_profile_key(tmp_path) -> None:
    p = tmp_path / "profiles.toml"
    p.write_text('[profiles.x]\nmoodel = "typo"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="unknown key"):
        load_profiles({"ARIADNE_PROFILES": str(p)})


def test_strict_parse_rejects_unknown_envelope_key(tmp_path) -> None:
    p = tmp_path / "profiles.toml"
    p.write_text(
        '[profiles.x]\nmodel = "m"\n[profiles.x.envelope]\nmax_turn = 5\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="envelope has unknown key"):
        load_profiles({"ARIADNE_PROFILES": str(p)})


def test_missing_profiles_file_names_the_env_var(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="ARIADNE_PROFILES"):
        load_profiles({"ARIADNE_PROFILES": str(tmp_path / "nope.toml")})
