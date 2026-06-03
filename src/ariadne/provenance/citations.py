"""Citation extraction and coverage validation.

The analytic note cites graph facts as ``[cite:gN]``. A note PASSES validation
only when all of these hold:

- **Precision (no dangling)** — every ``[cite:gN]`` resolves to a ledger entry
  (no fabricated sources).
- **Recall (coverage)** — every asserted claim carries a citation; a note may
  not assert a fact it did not retrieve.
- **Precision (entailment, Stage 2, optional)** — the cited ledger evidence
  actually *supports* the claim, checked by an injected ``EntailmentVerifier``.
  Skipped when no verifier is supplied, so the default path stays hermetic.

Recall and entailment are the two numbers ALCE (Gao et al., EMNLP 2023,
arXiv:2305.14627) calls citation *recall* and *precision*.
``# research(2026-06): ALCE citation precision/recall + HHEM entailment.``

Citable sections require a citation per claim; the note template marks **Gaps &
caveats** as "citations optional" and **Provenance** echoes raw ledger queries,
so both are exempt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from ariadne.provenance.tradecraft import is_estimative as _is_estimative

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from ariadne.provenance.ledger import ProvenanceLedger

_CITE_RE = re.compile(r"\[cite:(g\d+)\]")
_HEADER_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*)$")
_BULLET_RE = re.compile(r"^[\s>*+\-]+")
_NUMBERED_RE = re.compile(r"^\d+\.\s+")
_HAS_LETTER_RE = re.compile(r"[A-Za-z]")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

# Sections whose claims do not require a citation. Matched case-insensitively as
# a substring of the section header text.
_EXEMPT_SECTION_KEYWORDS = ("gaps", "provenance")


class EntailmentVerifier(Protocol):
    """Checks whether ``evidence`` supports ``claim``. Implemented by HHEM et al."""

    def entails(self, claim: str, evidence: str) -> bool: ...


@dataclass(frozen=True)
class CitationReport:
    """Result of validating a note's citations against a ledger."""

    ok: bool
    cited: list[str]
    dangling: list[str]  # cited in the note but absent from the ledger (failure)
    unused: list[str]  # in the ledger but never cited (informational)
    uncited: list[str] = field(default_factory=list)  # asserted claims with no citation (failure)
    unsupported: list[str] = field(
        default_factory=list
    )  # claims the cited evidence does not entail


def extract_citations(note: str) -> list[str]:
    """Return unique ``gN`` ids in first-seen order."""
    seen: dict[str, None] = {}
    for match in _CITE_RE.finditer(note):
        seen.setdefault(match.group(1), None)
    return list(seen)


def _iter_claim_segments(
    note: str, exempt_keywords: tuple[str, ...]
) -> Iterator[tuple[list[str], int]]:
    """Yield ``(sentences, last_cited_index)`` for each content line that may carry claims.

    Skips markdown headers, blank lines, fenced code, and any section whose
    header matches an exempt keyword (Gaps & caveats, Provenance). Leading bullet
    and list markers are stripped. ``last_cited_index`` is the index of the last
    sentence carrying a ``[cite:gN]`` (-1 if none) — a trailing citation covers
    everything up to it, since notes cite a multi-sentence bullet once at the end.
    """
    in_exempt = False
    in_code = False
    for raw in note.splitlines():
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not stripped:
            continue
        header = _HEADER_RE.match(raw)
        if header:
            in_exempt = any(k in header.group(1).lower() for k in exempt_keywords)
            continue
        if in_exempt:
            continue
        line = _NUMBERED_RE.sub("", _BULLET_RE.sub("", raw)).strip()
        sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(line) if s.strip()]
        last_cited = max((i for i, s in enumerate(sentences) if _CITE_RE.search(s)), default=-1)
        yield sentences, last_cited


def find_uncited_claims(
    note: str, *, exempt_keywords: tuple[str, ...] = _EXEMPT_SECTION_KEYWORDS
) -> list[str]:
    """Return the asserted claim sentences that carry no ``[cite:gN]`` (recall).

    Only prose sentences that fall *after* a segment's last citation (or a
    segment with no citation at all) count as uncited; a trailing citation covers
    the sentences before it.
    """
    uncited: list[str] = []
    for sentences, last_cited in _iter_claim_segments(note, exempt_keywords):
        uncited.extend(
            s for i, s in enumerate(sentences) if i > last_cited and _HAS_LETTER_RE.search(s)
        )
    return uncited


def find_unsupported_claims(
    note: str,
    ledger: ProvenanceLedger,
    verifier: EntailmentVerifier,
    *,
    exempt_keywords: tuple[str, ...] = _EXEMPT_SECTION_KEYWORDS,
    is_estimative: Callable[[str], bool] = _is_estimative,
) -> list[str]:
    """Return cited claims whose cited ledger evidence does not entail them (precision).

    Only the *cited* portion of a segment (sentences up to its last citation) is
    checked — trailing uncited sentences are a recall failure, not an entailment
    one. The claim text (cite markers stripped) is checked by ``verifier`` against
    the concatenated excerpts of the ledger entries it cites.

    Estimative claims (analytic judgments with ICD-203 hedging) are exempt: an
    entailment model would reject a calibrated inference the evidence does not
    *literally* state, so they are governed by the tradecraft calibration lint, not
    here. They still must be cited (the recall gate applies).
    """
    excerpts = {e["id"]: e["response_excerpt"] for e in ledger.entries}
    unsupported: list[str] = []
    for sentences, last_cited in _iter_claim_segments(note, exempt_keywords):
        if last_cited < 0:
            continue
        cited_text = " ".join(sentences[: last_cited + 1])
        claim = _CITE_RE.sub("", cited_text).strip()
        if not _HAS_LETTER_RE.search(claim) or is_estimative(claim):
            continue
        cites = _CITE_RE.findall(cited_text)
        evidence = "\n".join(excerpts[c] for c in cites if c in excerpts)
        if not verifier.entails(claim, evidence):
            unsupported.append(claim)
    return unsupported


def validate_citations(
    note: str, ledger: ProvenanceLedger, verifier: EntailmentVerifier | None = None
) -> CitationReport:
    """Validate a note: precision (no dangling), recall (no uncited), and — when a
    ``verifier`` is supplied — entailment (no unsupported)."""
    cited = extract_citations(note)
    ledger_ids = [e["id"] for e in ledger.entries]
    dangling = [c for c in cited if not ledger.has(c)]
    unused = [i for i in ledger_ids if i not in cited]
    uncited = find_uncited_claims(note)
    unsupported = find_unsupported_claims(note, ledger, verifier) if verifier is not None else []
    return CitationReport(
        ok=not dangling and not uncited and not unsupported,
        cited=cited,
        dangling=dangling,
        unused=unused,
        uncited=uncited,
        unsupported=unsupported,
    )
