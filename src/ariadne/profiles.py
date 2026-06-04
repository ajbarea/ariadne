"""Curated model profiles (ADR-0013).

A user selects a profile by name; the operator curates the allowlist. A profile
binds a model to an operating envelope. Air-gap deployments omit cloud profiles, so
an analyst cannot select one — an unknown name is rejected with the valid names.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

_PROFILE_KEYS = frozenset({"model", "egress", "description", "envelope"})
_ENVELOPE_KEYS = frozenset({"max_turns", "max_thinking_tokens"})


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
    profile_path = Path(path)
    if not profile_path.is_file():
        raise FileNotFoundError(f"ARIADNE_PROFILES points to a missing file: {path!r}")
    data = tomllib.loads(profile_path.read_text(encoding="utf-8"))
    for name, spec in data.get("profiles", {}).items():
        # Validate profile keys
        unknown = set(spec) - _PROFILE_KEYS
        if unknown:
            raise ValueError(f"Profile {name!r} has unknown key(s): {', '.join(sorted(unknown))}")
        # Validate envelope keys
        env_spec = spec.get("envelope", {})
        unknown_env = set(env_spec) - _ENVELOPE_KEYS
        if unknown_env:
            raise ValueError(
                f"Profile {name!r} envelope has unknown key(s): {', '.join(sorted(unknown_env))}"
            )
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
