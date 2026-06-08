"""The network-egress sentinel — verifies the air-gapped posture (ADR-0012).

The read-only audit checks the ledger for write attempts; this is its network sibling:
intercept socket connect and enforce a host allowlist, so an in-enclave operation that
reaches a non-allowlisted host is caught rather than trusted-not-to-happen.
"""

from __future__ import annotations

import socket

import pytest

from ariadne.egress import EgressReport, EgressViolation, _is_local, egress_guard


def test_is_local_recognizes_loopback() -> None:
    assert _is_local("127.0.0.1")
    assert _is_local("127.0.0.5")  # all of 127.0.0.0/8
    assert _is_local("::1")
    assert _is_local("localhost")
    assert not _is_local("8.8.8.8")
    assert not _is_local("api.anthropic.com")


def test_report_allows_loopback_and_allowlisted_hosts() -> None:
    r = EgressReport(block=True, allowed=frozenset({"db.enclave"}))
    r._check("127.0.0.1", 7687)  # loopback always allowed
    r._check("db.enclave", 5432)  # explicitly allowlisted enclave host
    assert r.ok


def test_report_blocks_a_nonlocal_host_when_blocking() -> None:
    r = EgressReport(block=True, allowed=frozenset())
    with pytest.raises(EgressViolation):
        r._check("8.8.8.8", 53)


def test_report_records_without_raising_in_audit_mode() -> None:
    """block=False is the runtime-audit mode: observe egress, don't break the app."""
    r = EgressReport(block=False, allowed=frozenset())
    r._check("api.example.com", 443)  # does not raise
    assert not r.ok
    assert r.violations == [("api.example.com", 443)]


def test_guard_blocks_a_real_nonlocal_connect() -> None:
    """The guard raises before the real connect (TEST-NET-3 never routes; stays hermetic)."""
    with egress_guard(), pytest.raises(EgressViolation):
        socket.create_connection(("203.0.113.1", 80), timeout=1)


def test_guard_passes_loopback_through_to_a_normal_socket_error() -> None:
    """Loopback is allowed: the connect itself fails (no listener) with a plain OSError,
    not an EgressViolation — proving the guard passed it through rather than blocking it."""
    with egress_guard():
        with pytest.raises(OSError) as ei:
            socket.create_connection(("127.0.0.1", 1), timeout=0.3)
        assert not isinstance(ei.value, EgressViolation)


def test_guard_restores_socket_methods_on_exit() -> None:
    before = socket.socket.connect
    with egress_guard():
        assert socket.socket.connect is not before
    assert socket.socket.connect is before


def test_guard_threads_allow_hosts_into_the_report() -> None:
    with egress_guard(allow_hosts=["db.enclave"]) as rep:
        assert "db.enclave" in rep.allowed
