"""Network-egress verification — the security / data-integrity axis of governance.

[ADR-0012](docs/architecture/decisions/0012-cloud-vs-air-gapped-deployment-fork.md) fixes
the cloud <-> air-gapped fork at a **single seam** — the orchestrator model at
``ANTHROPIC_BASE_URL``; everything else (connectors, embedder, entailment, stores) is
in-enclave. This *verifies* that posture the same way ``audit_read_only`` verifies the
read-only contract: don't trust the config, check the actual behaviour. ``egress_guard``
intercepts socket ``connect`` and enforces a host allowlist (loopback always allowed), so
an in-enclave operation that reaches a non-allowlisted host is caught — blocking (a CI/test
gate that fails on new egress) or recording (a runtime audit that observes without breaking
the app).

**Scope:** connection-time TCP enforcement (``socket.connect`` / ``connect_ex``) — the
chokepoint every connection-oriented client passes through (the Anthropic API via httpx,
Neo4j bolt, Postgres, Hugging Face model fetches). DNS-only resolution and connectionless
UDP sends are out of scope: neither moves application data, and ``getaddrinfo`` constructs
no socket so it cannot be reached this way regardless.

# research(2026-06): treat egress as a first-class allowlist + a CI check that fails on new
# egress (air-gapped LLM blueprint, tianpan.co 2026-05); intercept at connect, not socket
# creation — getaddrinfo bypasses socket-class patching (PySocks #22); allowed_hosts policy
# shape mirrors agent-airlock's NetworkPolicy. The monkeypatch is scoped to this guard, a
# verification tool, never production code.
"""

from __future__ import annotations

import socket
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Buffer, Iterable, Iterator
    from typing import Any

    # The socket-address shape stdlib's connect accepts (typeshed's ``_Address``).
    _Address = tuple[Any, ...] | str | Buffer

_LOOPBACK = frozenset({"localhost", "::1"})


class EgressViolation(RuntimeError):
    """A blocking ``egress_guard`` saw a connect to a non-allowlisted host."""


def _is_local(host: str) -> bool:
    """Loopback — the whole ``127.0.0.0/8`` block, ``::1``, and ``localhost``."""
    h = host.strip("[]").lower()
    return h in _LOOPBACK or h.startswith("127.")


@dataclass
class EgressReport:
    """The outcome of a guarded region: ``ok`` is False if any egress was attempted."""

    block: bool
    allowed: frozenset[str]
    violations: list[tuple[str, int]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def _check(self, host: str, port: int) -> None:
        if _is_local(host) or host.lower() in self.allowed:
            return
        self.violations.append((host, port))
        if self.block:
            raise EgressViolation(
                f"blocked egress to {host}:{port} — allowed: loopback + {sorted(self.allowed)}"
            )


def _peer_hostport(address: _Address) -> tuple[str, int] | None:
    """The (host, port) of a connect target; ``None`` for AF_UNIX paths (local IPC)."""
    if not isinstance(address, tuple) or not address:  # AF_UNIX str/bytes path — never egress
        return None
    port = address[1] if len(address) > 1 else 0
    return str(address[0]), port if isinstance(port, int) else 0


@contextmanager
def egress_guard(allow_hosts: Iterable[str] = (), *, block: bool = True) -> Iterator[EgressReport]:
    """Enforce (or audit) a network-egress allowlist for the duration of the ``with`` block.

    Loopback is always allowed; ``allow_hosts`` adds enclave hosts (e.g. the Neo4j/Postgres
    services). ``block=True`` raises :class:`EgressViolation` on the first non-allowlisted
    connect (the CI/test gate); ``block=False`` records every attempt into the yielded report
    without interrupting (the runtime audit). Restores the original socket methods on exit.
    """
    report = EgressReport(block=block, allowed=frozenset(h.lower() for h in allow_hosts))
    orig_connect = socket.socket.connect
    orig_connect_ex = socket.socket.connect_ex

    def _inspect(address: _Address) -> None:
        hp = _peer_hostport(address)
        if hp is not None:
            report._check(*hp)

    # Untyped self mirrors the stdlib method's implicit self, so the reassignment type-checks.
    def connect(self, address: _Address, /) -> None:
        _inspect(address)
        return orig_connect(self, address)

    def connect_ex(self, address: _Address, /) -> int:
        _inspect(address)
        return orig_connect_ex(self, address)

    # Intentional class-method monkeypatch (the verification mechanism); ty can't model a
    # method reassignment even with a matching signature.
    socket.socket.connect = connect  # ty: ignore[invalid-assignment]
    socket.socket.connect_ex = connect_ex  # ty: ignore[invalid-assignment]
    try:
        yield report
    finally:
        socket.socket.connect = orig_connect
        socket.socket.connect_ex = orig_connect_ex
