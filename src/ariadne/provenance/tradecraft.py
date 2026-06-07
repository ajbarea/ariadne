"""ICD-203 tradecraft lint — estimative-language standardization.

Intelligence Community Directive 203 fixes a seven-band Words-of-Estimative-
Probability scale and requires expressing **likelihood** (probability of an event)
separately from **analytic confidence** (quality of the underlying sourcing).
LLMs are measurably miscalibrated on these terms, so this lint surfaces:

- standard WEP terms used, with their probability band,
- non-standard estimative hedges ("possibly", "perhaps", ...) that should be
  replaced with a standard band,
- whether the note states analytic confidence at all.

Advisory (not a hard gate) — it reports, it does not fail the run.

# research(2026-06): ICD-203 WEP bands + likelihood/confidence split; LLMs
# diverge from the human WEP distributions (arXiv:2405.15185). Bands per the
# DNI directive (dni.gov/files/documents/ICD/ICD-203.pdf), cross-checked against
# the CIS/MS-ISAC WEP reference.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Standard WEP term (lowercase) -> probability band. Synonyms share a band.
_TERM_BANDS: dict[str, str] = {
    "almost no chance": "1-5%",
    "remote": "1-5%",
    "very unlikely": "5-20%",
    "highly improbable": "5-20%",
    "unlikely": "20-45%",
    "improbable": "20-45%",
    "roughly even chance": "45-55%",
    "roughly even odds": "45-55%",
    "likely": "55-80%",
    "probable": "55-80%",
    "probably": "55-80%",
    "very likely": "80-95%",
    "highly probable": "80-95%",
    "almost certain": "95-99%",
    "almost certainly": "95-99%",
    "nearly certain": "95-99%",
}

# Longest terms first so "very likely" wins over "likely" at the same position.
_WEP_RE = re.compile(
    r"\b(" + "|".join(sorted(map(re.escape, _TERM_BANDS), key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

# Estimative hedges that are NOT on the ICD-203 scale and should be replaced.
_NONSTANDARD = (
    "possibly",
    "perhaps",
    "maybe",
    "potentially",
    "conceivably",
    "presumably",
    "arguably",
)
_NONSTANDARD_RE = re.compile(r"\b(" + "|".join(_NONSTANDARD) + r")\b", re.IGNORECASE)

_CONFIDENCE_RE = re.compile(r"\b(?:low|moderate|high)\s+confidence\b", re.IGNORECASE)

# Inference/reasoning connectives that mark an analytic JUDGMENT (vs a sourced
# fact). Heuristic; pairs with is_estimative (WEP/hedge/confidence).
#
# research(2026-06): illative (conclusion-indicating) connectives — therefore,
# thus, hence, consequently, accordingly, it follows that, entails — plus the
# self-labels inferred/inference. These are the standard logic "conclusion
# indicators"; REASON indicators (because, since, so) are deliberately excluded
# because they introduce premises that may be sourced facts, which would risk
# exempting a genuine uncited fact (only trailing sentences in an already-cited
# segment are exempt, so the conclusion-side markers are the safe set). Source:
# argument-mapping conclusion/premise indicator lists, cross-checked 2026-06.
_INFERENCE_MARKERS = (
    "suggests",
    "indicates",
    "implies",
    "entails",
    "consistent with",
    "in other words",
    "points to",
    "reflects",
    "reveals",
    "understates",
    "plausibly",
    "appears to",
    "means that",
    "signature of",
    "rather than",
    "would ",
    "therefore",
    "thus",
    "hence",
    "consequently",
    "accordingly",
    "it follows that",
    "inferred",
    "inference",
)
_INFERENCE_RE = re.compile("|".join(re.escape(m) for m in _INFERENCE_MARKERS), re.IGNORECASE)


@dataclass(frozen=True)
class TradecraftReport:
    """ICD-203 estimative-language findings for a note (advisory)."""

    standard_terms: list[tuple[str, str]] = field(default_factory=list)  # (term, band)
    nonstandard_terms: list[str] = field(default_factory=list)
    has_confidence_statement: bool = False


def is_estimative(text: str) -> bool:
    """True if ``text`` carries an analytic judgment (WEP term, hedge, or confidence).

    Such a claim is a calibrated *inference*, not a fact the evidence directly
    entails, so the entailment gate must route it here (the calibration lint)
    rather than reject it. Uses the same ICD-203 vocabulary as the lint.
    """
    return bool(_WEP_RE.search(text) or _NONSTANDARD_RE.search(text) or _CONFIDENCE_RE.search(text))


def is_analytic_judgment(text: str) -> bool:
    """True if ``text`` reads as an analytic judgment/inference rather than a
    sourced fact (estimative language or inference connectives).

    # research(2026-06): ICD-206 — a judgment must cite the source it *depends
    # on*; one grounded by evidence cited in the same segment need not repeat the
    # cite. Distinguished from facts per ICD-203. Heuristic marker set; `would `
    # (trailing space) targets modal/inferential use.
    """
    return is_estimative(text) or bool(_INFERENCE_RE.search(text))


# Statements of evidential LIMIT / insufficiency — what the evidence does NOT
# establish, or which modalities were unavailable. Like estimative hedges, these are
# analytic-confidence calibration, not evidence claims, so ICD-206 governs them via
# this lint rather than the cite gate.
_CAVEAT_MARKERS = (
    "cannot be ruled out",
    "cannot be confirmed",
    "cannot be established",
    "cannot be verified",
    "cannot be determined",
    "could not be confirmed",
    "without a second",
    "without additional",
    "without corroborat",
    "needs corroboration",
    "requires corroboration",
    "requires a second",
    "insufficient evidence",
    "no direct evidence",
    "remains unconfirmed",
    "remains tentative",
    "single modality",
    "single-modality",
)
# Sole-modality phrasings that aren't fixed strings ("rests on the graph alone",
# "this modality alone"): one analysis modality was used — an evidential limit. The
# noun set is analysis-methodology terms only, so "a single source of funding alone"
# (an entity claim) is NOT exempted.
_CAVEAT_PATTERNS = (r"\b(?:graph|modality|evidence)\s+alone\b",)
_CAVEAT_RE = re.compile(
    "|".join([*(re.escape(m) for m in _CAVEAT_MARKERS), *_CAVEAT_PATTERNS]),
    re.IGNORECASE,
)


def is_analytic_caveat(text: str) -> bool:
    """True if ``text`` states an evidential LIMIT (what the evidence does not
    establish) rather than asserting an evidence claim.

    # research(2026-06): ICD-206 separates analytic judgments (which must cite their
    # basis) from confidence/limitation statements. "X cannot be ruled out without a
    # second modality" asserts insufficiency, not a fact — so it is governed by the
    # calibration lint, not the citation-recall gate.
    """
    return bool(_CAVEAT_RE.search(text))


def lint_estimative_language(note: str) -> TradecraftReport:
    """Report ICD-203 estimative-language usage in ``note`` (does not fail the note)."""
    standard = [
        (m.group(0).lower(), _TERM_BANDS[m.group(0).lower()]) for m in _WEP_RE.finditer(note)
    ]
    nonstandard = [m.group(0).lower() for m in _NONSTANDARD_RE.finditer(note)]
    return TradecraftReport(
        standard_terms=standard,
        nonstandard_terms=nonstandard,
        has_confidence_statement=bool(_CONFIDENCE_RE.search(note)),
    )
