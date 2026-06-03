"""HHEM-backed entailment verifier for citation precision (Stage 2).

Wraps Vectara's HHEM-2.1-Open hallucination-detection model as an
``EntailmentVerifier`` (see ``citations.EntailmentVerifier``). The model and its
dependencies live behind the optional ``eval`` extra and are imported lazily, so
the core package stays lightweight and the default (no-verifier) validation path
needs no model.

# research(2026-06): HHEM-2.1-Open — open, CPU-friendly (<600MB RAM,
# ~1.5s/2k-token input), the backend of RAGAS's FaithfulnessWithHHEM. Score in
# [0,1], higher = more supported; input pair order is (premise, hypothesis) =
# (evidence, claim). https://huggingface.co/vectara/hallucination_evaluation_model
#
# Caveat (docs/research/analytic-rigor-eval.md): NLI models are trained on
# factual entailment and may misjudge estimative/hedged analytic language
# ("likely", "moderate confidence") — validate on a hedged-claim set before
# trusting the gate.
"""

from __future__ import annotations

_MODEL_NAME = "vectara/hallucination_evaluation_model"


class HHEMVerifier:
    """An ``EntailmentVerifier`` backed by HHEM-2.1-Open. Requires the ``eval`` extra."""

    def __init__(self, *, threshold: float = 0.5, model_name: str = _MODEL_NAME) -> None:
        # Dynamic import: `transformers` is the optional `eval` extra, so the
        # static checker must not try to resolve it whether or not it's installed.
        import importlib

        transformers = importlib.import_module("transformers")
        self._model = transformers.AutoModelForSequenceClassification.from_pretrained(
            model_name, trust_remote_code=True
        )
        self._threshold = threshold

    def entails(self, claim: str, evidence: str) -> bool:
        """True when HHEM scores the (evidence → claim) pair at or above the threshold.

        Empty evidence (e.g. a claim whose only citations are dangling) is treated
        as unsupported.
        """
        if not evidence.strip():
            return False
        score = float(self._model.predict([(evidence, claim)])[0])
        return score >= self._threshold
