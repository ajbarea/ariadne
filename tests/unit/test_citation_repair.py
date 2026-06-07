from __future__ import annotations

from ariadne.provenance.ledger import ProvenanceLedger
from ariadne.provenance.repair import (
    build_repair_prompt,
    repair_citations,
    repair_citations_loop,
)


def _ledger() -> ProvenanceLedger:
    led = ProvenanceLedger()
    led.record(
        "mcp__neo4j__read_neo4j_cypher",
        {"query": "MATCH (h:Person {alias:'H1'}) RETURN h"},
        "Halberd leads Signals-Cell",
    )
    led.record(
        "mcp__postgres__execute_sql",
        {"sql": "SELECT cover_employer FROM personnel WHERE alias='H1'"},
        "cover_employer=Meridian Freight Ltd",
    )
    return led


def test_build_repair_prompt_includes_note_ledger_and_flagged_claims() -> None:
    led = _ledger()
    note = "## Summary\nHalberd leads Signals-Cell [cite:g1].\n\n## ACH\nH1 is favored.\n"
    uncited = ["H1 is favored."]
    prompt = build_repair_prompt(note, led.entries, uncited)

    # The draft is included verbatim so the model sees where g1 was already cited.
    assert "Halberd leads Signals-Cell [cite:g1]" in prompt
    # Every ledger id and a slice of its evidence is available to ground a cite.
    assert "g1" in prompt
    assert "g2" in prompt
    assert "Halberd leads Signals-Cell" in prompt  # g1 excerpt
    assert "Meridian Freight Ltd" in prompt  # g2 excerpt
    # The flagged claim is called out for repair.
    assert "H1 is favored." in prompt
    # The cite format is shown so the model attaches the existing-id form.
    assert "[cite:g" in prompt


async def test_repair_citations_builds_prompt_and_returns_llm_revision() -> None:
    led = _ledger()
    note = "## ACH\nH1 is favored.\n"
    seen: dict[str, str] = {}

    async def fake_llm(prompt: str) -> str:
        seen["prompt"] = prompt
        return "## ACH\nH1 is favored [cite:g1].\n"

    out = await repair_citations(note, led, ["H1 is favored."], call_llm=fake_llm)

    assert "H1 is favored." in seen["prompt"]  # prompt was built from the inputs
    assert out == "## ACH\nH1 is favored [cite:g1].\n"  # returns the model's revision


async def test_repair_loop_grounds_uncited_claims_within_bound() -> None:
    led = _ledger()
    note = "## Summary\nHalberd leads Signals-Cell [cite:g1].\n\n## ACH\nH1 is favored.\n"

    async def fixing_llm(prompt: str) -> str:
        return note.replace("H1 is favored.", "H1 is favored [cite:g1].")

    repaired, report = await repair_citations_loop(note, led, call_llm=fixing_llm)

    assert report.ok is True
    assert report.uncited == []
    assert "H1 is favored [cite:g1]." in repaired


async def test_repair_loop_is_bounded_when_the_model_cannot_fix() -> None:
    led = _ledger()
    note = "## ACH\nH1 is favored.\n"
    calls = {"n": 0}

    async def stubborn_llm(prompt: str) -> str:
        calls["n"] += 1
        return note  # never grounds the claim

    _, report = await repair_citations_loop(note, led, call_llm=stubborn_llm, max_passes=2)

    assert report.ok is False
    assert report.uncited  # still flagged, no infinite loop
    assert calls["n"] == 2  # bounded to exactly max_passes attempts


async def test_repair_loop_threads_the_entailment_verifier_and_skips_unsupported() -> None:
    # Repair targets recall (uncited), not precision (unsupported). With a fully-cited
    # note and a reject-all verifier, the loop must surface the entailment failure in
    # the final report yet NOT call the model (nothing uncited to repair).
    led = _ledger()
    note = "## Summary\nHalberd leads Signals-Cell [cite:g1].\n"
    calls = {"n": 0}

    class RejectAll:
        def entails(self, claim: str, evidence: str) -> bool:
            return False

    async def llm(prompt: str) -> str:
        calls["n"] += 1
        return note

    _, report = await repair_citations_loop(note, led, call_llm=llm, verifier=RejectAll())

    assert report.unsupported  # verifier was applied in the final validation
    assert calls["n"] == 0  # nothing uncited -> no repair pass fired
