# 0033, Verifying the air-gapped posture — a network-egress guard

- **Status:** Accepted (2026-06-08)
- **Deciders:** Ariadne maintainers
- **Touches:** `egress.py` (new), `tests/unit/conftest.py` (autouse CI gate), `tests/unit/test_egress_guard.py`

## Context

[ADR-0012](0012-cloud-vs-air-gapped-deployment-fork.md) makes a strong claim: the
cloud ↔ air-gapped fork is a **single seam** — the orchestrator model at
`ANTHROPIC_BASE_URL` — and *everything else* (connectors, embedder, entailment,
stores) is in-enclave or self-hostable, with the local-first embedder/multimodal
choices (ADR-0007/0008) pre-empting the classic embedding-egress leak. That claim is
load-bearing for any SCADS on-prem deployment, yet **nothing verified it**. The codebase
already rejects "trust the config" elsewhere: `audit_read_only` ([provenance/governance.py](../../../src/ariadne/provenance/governance.py))
audits the *actual* tool trace for write attempts rather than trusting the connector's
read-only flag. Network egress had no equivalent — a dependency, a telemetry exporter, or
a model download could reach out and no test would notice.

## Decision drivers

- **Verify the posture, don't assume it** — the same defence-in-depth principle as the
  read-only audit, applied to the network axis.
- **Free / hermetic** — must run with zero API spend and no live stores, so it can be an
  always-on CI gate, not a manual exercise.
- **Catch regressions** — the 2026 air-gapped consensus is an explicit egress allowlist
  *plus a CI check that fails the build when new egress appears*, not a one-time audit.
- **Minimal surface** — own the primitive (like the read-only audit) rather than take a
  dependency for ~50 lines.

## Considered options

1. **`pytest-socket` (the de-facto plugin).** Battle-tested, patches `socket.socket`.
   *Cons:* a new dev dependency; CI-test-only (not reusable as a runtime audit); patching
   the socket *class* misses `getaddrinfo` (PySocks #22) — but so does any approach, and it
   over-blocks at creation rather than at the egress moment.
2. **`agent-airlock` (2026 `NetworkPolicy`).** Modern, the right `allowed_hosts` shape.
   *Cons:* heavier dependency for a guard; designed for sandboxing agents, not verifying our
   own in-enclave code.
3. **Own a small connect-level sentinel (chosen).** Intercept `socket.connect` /
   `connect_ex` — the chokepoint every connection-oriented client (httpx → Anthropic API,
   Neo4j bolt, Postgres, HF fetches) must pass — and enforce a loopback-plus-allowlist
   policy. *Pros:* no dependency; mirrors `audit_read_only`; one primitive serves **both** a
   blocking CI gate **and** a non-blocking runtime audit; borrows `agent-airlock`'s
   `allowed_hosts` shape. *Cons:* a deliberate monkeypatch (scoped to the guard, never prod);
   covers TCP connect only.

## Decision

Add `ariadne.egress` — `egress_guard(allow_hosts=(), *, block=True)`, a context manager that
patches `socket.connect` / `connect_ex` for its duration and routes every connect target
through an allowlist (loopback always allowed). `block=True` raises `EgressViolation` on the
first non-allowlisted connect (the gate); `block=False` records attempts into the yielded
`EgressReport` without interrupting (the runtime audit). An **autouse fixture in the unit
suite** wraps every unit test in `egress_guard(block=True)`, so the in-enclave code — as
exercised by 490+ hermetic tests — is **continuously proven** to make zero non-loopback
egress, and any future test or code that reaches out fails the build. Integration tests,
which legitimately talk to enclave stores, keep their own conftest and are unaffected.

**Scope, stated honestly:** connection-time TCP enforcement only. DNS-only resolution and
connectionless UDP `sendto` are out of scope — neither moves application data, and
`getaddrinfo` constructs no socket, so it is unreachable this way regardless. Every network
client Ariadne actually uses is connection-oriented, so the chokepoint is complete for the
real surface.

## Consequences

- The ADR-0012 single-seam claim is now a *verified, regression-guarded* property of the
  hermetic surface, not prose — and the same primitive is ready to wrap a live workup
  (`block=False`) for the on-prem-store runtime audit when stores are up.
- The guard is a deliberate monkeypatch; ty cannot model a class-method reassignment even
  with a matching signature, so the two patch lines carry a scoped `# ty: ignore`.
- It does not replace network-layer enforcement (a default-deny egress policy in
  production) — it is the application-level *verification* that complements it, exactly as
  the read-only audit complements the connector's restricted mode.

## Sources

- [The air-gapped LLM blueprint — egress as a first-class allowlist + CI fail-on-new-egress (tianpan.co, 2026-05)](https://tianpan.co/blog/2026-05-01-air-gapped-llm-blueprint-egress-free-deployment)
- [pytest-socket](https://github.com/miketheman/pytest-socket) · [agent-airlock `NetworkPolicy`](https://pypi.org/project/agent-airlock/) · [PySocks #22 — `getaddrinfo` bypasses socket-class patching](https://github.com/Anorov/PySocks/issues/22)
- [ADR-0012](0012-cloud-vs-air-gapped-deployment-fork.md) (the claim) · the `audit_read_only` precedent (`provenance/governance.py`)
