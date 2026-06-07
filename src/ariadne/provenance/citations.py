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

import pysbd

from ariadne.provenance.tradecraft import (
    is_analytic_caveat as _is_analytic_caveat,
    is_analytic_judgment as _is_analytic_judgment,
    is_estimative as _is_estimative,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from ariadne.provenance.ledger import ProvenanceLedger

_CITE_RE = re.compile(r"\[cite:(g\d+)\]")
_HEADER_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*)$")
_BULLET_RE = re.compile(r"^[\s>*+\-]+")
_NUMBERED_RE = re.compile(r"^\d+\.\s+")
_HAS_LETTER_RE = re.compile(r"[A-Za-z]")

# research(2026-06): pysbd rule-based SBD is abbreviation-aware (i.e./e.g./U.S.)
# and dependency-free, so it won't split a cited sentence on an internal "." the
# way a naive `(?<=[.!?])\s+` regex did (ADR-0022; arXiv:2010.09657).
_SEGMENTER = pysbd.Segmenter(language="en", clean=False)

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


@dataclass(frozen=True)
class CoverageStats:
    """Claim-level structural citation coverage of a note (ADR-0023).

    ``covered`` citable claims carry — or are covered by — an in-segment
    ``[cite:gN]``; ``total`` is the recall gate's full citable-claim universe
    (``covered`` + uncited), so ``fraction`` is ``1.0`` exactly when
    ``find_uncited_claims`` is empty. ``fraction`` is ``None`` when a note has no
    citable claim (undefined, not zero). This is the measurement the P-Cite repair
    loop moves; precision (entailment) is a separate axis. ``# research(2026-06):
    Coverage = proportion of attribution present, P-Cite > G-Cite (arXiv:2509.21557).``
    """

    covered: int
    total: int
    fraction: float | None


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
        if stripped.startswith("|"):  # markdown table row/separator — not a prose claim
            continue
        line = _NUMBERED_RE.sub("", _BULLET_RE.sub("", raw)).strip()
        sentences = [s.strip() for s in _SEGMENTER.segment(line) if s.strip()]
        last_cited = max((i for i, s in enumerate(sentences) if _CITE_RE.search(s)), default=-1)
        yield sentences, last_cited


def _iter_citable_claims(
    note: str,
    exempt_keywords: tuple[str, ...],
    is_judgment: Callable[[str], bool],
    is_caveat: Callable[[str], bool],
) -> Iterator[tuple[str, bool]]:
    """Yield ``(sentence, covered)`` for each *citable* claim sentence in the note.

    A citable claim asserts something that needs a citation, so non-claims are
    excluded: headers / blanks / fenced code / exempt sections (upstream in
    ``_iter_claim_segments``), plus table rows, colon lead-ins, and ICD-206
    evidential-limit caveats. ``covered`` is True when the sentence carries or is
    covered by an in-segment ``[cite:gN]`` — including a trailing analytic judgment
    grounded by a cite earlier in its segment (ICD-206) — else False (uncited).

    The single source of truth for both the recall gate (``find_uncited_claims``)
    and the coverage metric (``citation_coverage``), so the two cannot diverge.
    """
    for sentences, last_cited in _iter_claim_segments(note, exempt_keywords):
        for i, s in enumerate(sentences):
            if not _HAS_LETTER_RE.search(s) or s.rstrip().endswith(":") or is_caveat(s):
                continue
            yield s, (i <= last_cited or (last_cited >= 0 and is_judgment(s)))


def find_uncited_claims(
    note: str,
    *,
    exempt_keywords: tuple[str, ...] = _EXEMPT_SECTION_KEYWORDS,
    is_judgment: Callable[[str], bool] = _is_analytic_judgment,
    is_caveat: Callable[[str], bool] = _is_analytic_caveat,
) -> list[str]:
    """Return the asserted claim sentences that carry no ``[cite:gN]`` (recall).

    Only prose sentences *after* a segment's last citation (or in a segment with no
    citation at all) count as uncited; a trailing citation covers the sentences
    before it. Analytic judgments trailing a segment that ALREADY carries a citation
    are exempt (ICD-206 — they rest on evidence cited in the same segment); facts,
    and any claim in an uncited segment, are flagged regardless.
    """
    claims = _iter_citable_claims(note, exempt_keywords, is_judgment, is_caveat)
    return [s for s, covered in claims if not covered]


def citation_coverage(
    note: str,
    *,
    exempt_keywords: tuple[str, ...] = _EXEMPT_SECTION_KEYWORDS,
    is_judgment: Callable[[str], bool] = _is_analytic_judgment,
    is_caveat: Callable[[str], bool] = _is_analytic_caveat,
) -> CoverageStats:
    """Structural citation coverage: covered citable claims / total citable claims.

    The claim universe is exactly the one ``find_uncited_claims`` walks (both derive
    from ``_iter_citable_claims``), so coverage is ``1.0`` iff that gate is clean.
    ``fraction`` is ``None`` when the note has no citable claim (undefined, not 0).
    The measurement the P-Cite repair loop moves; precision is a separate axis. ADR-0023.
    """
    covered = total = 0
    for _s, is_covered in _iter_citable_claims(note, exempt_keywords, is_judgment, is_caveat):
        total += 1
        covered += int(is_covered)
    return CoverageStats(covered, total, covered / total if total else None)


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
