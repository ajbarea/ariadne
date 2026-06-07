"""Post-hoc citation repair (P-Cite) — close the recall coverage gap.

The agent drafts the note with inline ``[cite:gN]`` (Generation-Time Citation),
which is precision-first but structurally under-covers: synthesis / ACH judgment
sentences land without the cite of their basis. After the deterministic recall gate
finds those uncited claims, a bounded post-hoc pass attaches the ``[cite:gN]`` from
the existing ledger (or softens an ungroundable claim). The gate, not the model,
terminates the loop — sidestepping self-refinement degradation.

``# research(2026-06): P-Cite-first for high-stakes attribution (arXiv:2509.21557);
bounded, deterministically-terminated refinement (arXiv:2303.17651). ADR-0022.``
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from ariadne.provenance.citations import validate_citations

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from ariadne.provenance.citations import CitationReport, EntailmentVerifier
    from ariadne.provenance.ledger import ProvenanceLedger

# research(2026-06): bound the passes + let the deterministic gate (not the model)
# terminate, to avoid the self-refinement degradation of LLM self-judgment loops
# (arXiv:2303.17651). One P-Cite pass usually suffices. ADR-0022.
MAX_REPAIR_PASSES = 2


def _evidence_line(entry: dict[str, Any]) -> str:
    """Render one ledger entry as a citable ``[cite:gN] <query>`` + evidence excerpt."""
    tool_input = entry.get("tool_input") or {}
    query = tool_input.get("query") or tool_input.get("sql") or json.dumps(tool_input)
    return f"- [cite:{entry['id']}] {query}\n  evidence: {entry['response_excerpt']}"


def build_repair_prompt(note: str, ledger_entries: list[dict[str, Any]], uncited: list[str]) -> str:
    """Render the post-hoc repair instruction for one pass.

    Gives the model the full draft (so it sees where each ``gN`` was already cited in
    the supporting bullets), the ledger as ``gN -> query + evidence``, and the flagged
    sentences. The rule: attach an existing ``[cite:gN]`` to each flagged claim, or
    soften an ungroundable one; never fabricate an id; change nothing else.
    """
    evidence = "\n".join(_evidence_line(e) for e in ledger_entries)
    flagged = "\n".join(f"- {s}" for s in uncited)
    return (
        "You are repairing the citations on an analytic note. Each flagged sentence "
        "asserts a claim but carries no [cite:gN]. For EACH flagged sentence, append "
        "the [cite:gN](s) from the provenance ledger whose evidence supports it — "
        "usually the same ids already cited on the bullets the sentence summarizes. "
        "If NO ledger entry supports it, soften it to a calibrated ICD-203 judgment "
        "(likely / probable / unlikely, etc.) or delete it. Never invent a gN absent "
        "from the ledger; change nothing else; preserve all existing text and cites. "
        "Return ONLY the full corrected note in Markdown, with no preamble.\n\n"
        f"## Provenance ledger (the only citable evidence)\n{evidence}\n\n"
        f"## Flagged sentences (assert a claim, missing [cite:gN])\n{flagged}\n\n"
        f"## Note to correct\n{note}"
    )


async def repair_citations(
    note: str,
    ledger: ProvenanceLedger,
    uncited: list[str],
    *,
    call_llm: Callable[[str], Awaitable[str]],
) -> str:
    """Run one post-hoc pass: build the repair prompt, call the model, return its note."""
    prompt = build_repair_prompt(note, ledger.entries, uncited)
    return await call_llm(prompt)


async def repair_citations_loop(
    note: str,
    ledger: ProvenanceLedger,
    *,
    call_llm: Callable[[str], Awaitable[str]],
    verifier: EntailmentVerifier | None = None,
    max_passes: int = MAX_REPAIR_PASSES,
) -> tuple[str, CitationReport]:
    """Repair uncited claims until the deterministic gate is clean or the bound is hit.

    Only recall (``uncited``) is repaired; ``dangling`` / ``unsupported`` are surfaced
    in the returned report, not rewritten. The gate decides when to stop, so the loop
    cannot talk itself out of a correct note the way an LLM self-judge would.
    """
    report = validate_citations(note, ledger, verifier=verifier)
    for _ in range(max_passes):
        if report.ok or not report.uncited:
            break
        note = await repair_citations(note, ledger, report.uncited, call_llm=call_llm)
        report = validate_citations(note, ledger, verifier=verifier)
    return note, report
