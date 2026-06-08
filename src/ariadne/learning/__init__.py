"""Axis B — bounded, audited self-improvement (ADR-0020).

The learning the harness does *from experience*, on the propose -> ratify -> freeze
spine: it proposes declarative artifacts a human ratifies and the deterministic gates
keep checking; it never edits its gates, scorers, governance, or code. Members:
:mod:`ariadne.learning.distil` (B2 — learned analytic skills, ADR-0029),
:mod:`ariadne.learning.reflect` (B3 — reflexion over the eval harness, ADR-0030),
:mod:`ariadne.learning.netcheck` (the measured ratify step — ``compare``, ADR-0031), and
:mod:`ariadne.learning.ratify` (automated ratification — produce the paired runs, ADR-0034),
over the shared run model in :mod:`ariadne.learning.runs`.
"""

# The default Claude model for Axis B's LLM proposers (distiller / reflector).
DEFAULT_MODEL = "claude-opus-4-8"
