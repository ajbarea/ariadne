# Ariadne — Implementation scratchpad

What's being worked on **right now** — nothing else. Long-term plans and the
one-line ledger of completed work live in [ROADMAP.md](./ROADMAP.md); the full
record of *how* each thing shipped is in `docs/superpowers/plans/`, the ADRs
(`docs/architecture/decisions/`), and git history. Keep this file short: when a
task ships, move its one-liner to ROADMAP and clear it from here.

## In flight

_Nothing in flight._ Pick the next item from
[ROADMAP](./ROADMAP.md) — open candidates worth grabbing first:

- **`entity-workup` skill-prompt improvement** — prompt the agent to weigh
  alternatives, state implications, use WEP estimative terms + an analytic-
  confidence statement. Both the tradecraft lint and the new ICD-203 rubric show
  the live notes currently do little of this. Needs a live re-run to verify the
  scores move. _(Cheap, high-signal, fully autonomous.)_
- **Vector/unstructured connector re-research** — the deep-research run only
  adversarially confirmed the SQL choice; pgvector vs Redis-8 vs a dedicated
  store still needs its own clean pass before hardening.
- **Subagent fan-out design pass** — deferred (ADR-0005), not blocked on
  research; needs the provenance-redesign sketch before any code.

Blocked on AJ: Phase C / Avocado (licensed data), PyPI publish (token + name).
