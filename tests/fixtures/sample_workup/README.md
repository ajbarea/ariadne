# Sample workup fixture (CI governance gate)

A clean, read-only provenance ledger. The CI `governance` job runs
`ariadne governance tests/fixtures/sample_workup` against it as an end-to-end
smoke of the read-only contract gate — it must exit 0 because no ledger
statement carries a mutating verb. See `src/ariadne/provenance/governance.py`
and ADR-0003 (read-only/restricted store access).
