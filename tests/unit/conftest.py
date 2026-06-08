"""Unit tests are in-enclave by contract — they must make zero network egress.

This autouse guard fails any unit test that connects to a non-loopback host, turning
ADR-0012's air-gapped posture into a standing CI check: the moment a test (or the code it
exercises) reaches out to the network, the build fails. Loopback is allowed (a local fake
server is fine); nothing else is. Integration tests, which legitimately talk to enclave
stores, have their own conftest and are unaffected.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from ariadne.egress import egress_guard

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _no_network_egress() -> Iterator[None]:
    with egress_guard(block=True):
        yield
