# Analytic Rigor & Evaluation — "How Do You Know It Works?" (June 2026)

> **Provenance.** Synthesized 2026-06-02 from a deep-research pass on the brief's
> core challenge — **specification & validation** ("how do you know what works?")
> plus **governance** (quality, security, data integrity). Primary-source-backed;
> the harness's adversarial-verify stage was unreliable this run, so load-bearing
> claims were re-checked against their primary sources by hand. Decisions carry
> `# research(2026-06):` notes; unverified leads are flagged as such.

## Why this exists

Phase 1's citation gate proved only that the agent **did not fabricate a source**
(every `[cite:gN]` resolved to a ledger entry). It did **not** detect *uncited*
claims, the `SKILL.md` guarantee that "a note with an uncited claim fails
validation" was unenforced, and citations are recorded **per query**, not per
fact. This pass grounds the fix and the Phase 4 eval harness.

---

## Thread 1 — Citation groundedness (the gate)

The metric vocabulary is settled by **ALCE** (Gao et al., EMNLP 2023,
[arXiv:2305.14627](https://arxiv.org/abs/2305.14627)): `# research(2026-06):`

- **Citation recall** — is every claim supported by *a* cited source? → catches
  the *uncited-claim* hole.
- **Citation precision** — does each cited source actually *entail* the claim
  (not merely resolve as an id)? → catches the *entailment* hole.

Both are computed by an NLI/entailment model between claim and cited passage.

### Stage 1 — coverage / recall ✅ SHIPPED (2026-06-02)

`provenance/citations.find_uncited_claims` + `CitationReport.uncited`; a note now
fails validation if any asserted claim is uncited. Hermetic, no new dependency.
Section-aware (Gaps & caveats and Provenance are exempt per the note template);
segment-granular (a trailing citation covers its bullet/paragraph, so only prose
*after* a segment's last citation is flagged — this matches how the agent
actually cites and avoids false-positiving the real Halberd bridge bullet).
**Known limit:** structural recall only — it does not yet check entailment, and a
sentence sandwiched *before* a trailing citation is assumed covered. That is
Stage 2.

### Stage 2 — entailment / precision ✅ FRAMEWORK SHIPPED (2026-06-02)

`EntailmentVerifier` protocol + `find_unsupported_claims` + `CitationReport.unsupported`,
injected into `validate_citations(note, ledger, verifier=...)` — optional, so the
default path stays hermetic (unit-tested via a fake verifier). The real
`HHEMVerifier` (Vectara HHEM-2.1-Open, lazy-imported) lives behind the optional
`eval` extra with a gated integration test. Only the *cited* portion of a segment
is entailment-checked (trailing uncited prose is Stage 1's job). **Remaining:**
validate HHEM on a hedged-claim set, optionally wire a CLI `--entail` flag.

Candidate entailment models, with a *runnable-as-a-CI-gate* verdict:

| Model | Base / size | License | Gate verdict |
| --- | --- | --- | --- |
| **HHEM-2.1-Open** (via RAGAS `FaithfulnessWithHHEM`) | small T5 | open | ✅ hermetic, CPU — cheapest local path |
| **MiniCheck-Flan-T5-Large** | 770M | Apache-2.0 | ✅ GPU; "best <1B, reaches GPT-4" on LLM-AggreFact; sentence-level (decompose first) |
| **AlignScore-large** | 355M RoBERTa | open | ✅ fastest (~0.18s/ex) |
| **LIM-RA** | ~350M DeBERTa | open | ✅ best accuracy/size (SummaC bal-acc 78.5 vs AlignScore 74.0) |
| Bespoke-MiniCheck-7B | ~8B | commercial-gated | ⚠️ skip for a permissive repo |
| RAGAS-default / FActScore / ALCE-TRUE-11B | frontier judge | — | ⚠️ integration-tier (key-gated) only |

`# research(2026-06): ALCE precision/recall + MiniCheck/HHEM entailment.`
Lead: **HHEM-2.1-Open** for the hermetic gate, frontier-judge variant key-gated
like the existing live test. **The gap nobody solved:** uncited-*claim*
detection — Stage 1 above is that missing piece (decompose → coverage), now built.

> **Load-bearing caveat.** These NLI models are trained on *factual* entailment;
> analytic notes use *estimative/hedged* language ("likely", "assessed with
> moderate confidence"). Off-the-shelf entailment may misjudge hedged claims —
> validate against a small hedged-claim set before trusting Stage 2. Bridges to
> Thread 2.

## Thread 2 — Tradecraft compliance

- **ICD-203** (IC analytic standards;
  [fas.org PDF](https://fas.org/irp/dni/icd/icd-203.pdf)) defines the WEP
  probability bands and mandates a split Ariadne does not yet make: **likelihood
  of an event ≠ confidence in the basis** for the judgment. A compliant note
  needs both axes. `# research(2026-06):`
- LLMs are **measurably miscalibrated** on estimative language
  ([arXiv:2405.15185](https://arxiv.org/pdf/2405.15185): GPT-3.5/4 WEP
  distributions diverge from humans on 11–12 of 12 standard terms) — so enforce
  an explicit **WEP→numeric-band mapping as a lint**, don't assume "likely" means
  what ICD-203 says.
- **LLM-RUBRIC** ([arXiv:2501.00274](https://arxiv.org/pdf/2501.00274)) — a
  calibrated multidimensional automated-eval method; the path to scoring ICD-203
  as a rubric rather than a vibe check.
- **AgentCDM** ([arXiv:2508.11995](https://arxiv.org/pdf/2508.11995)) operationalizes
  **Analysis of Competing Hypotheses (ACH)** as multi-agent scaffolding with
  evidence matrices. *Caveat: cognitive-science ACH, not the IC/ICD-203 variant —
  direction, not method.* Bigger idea: ACH could reshape `entity-workup` from
  "synthesize a note" to "enumerate competing hypotheses → marshal cited evidence
  for/against each."

## Thread 3 — Eval harness for the four success criteria

The planted Compound-Alpha bridge in the seed graph is **latent ground truth**;
the literature supplies the metrics. `# research(2026-06):`

- **Multi-hop answer + supporting-evidence F1** is the standard — **MuSiQue**
  ([arXiv:2108.00573](https://arxiv.org/abs/2108.00573)) (2–4 hop, engineered
  against shortcuts) and **HotpotQA** supporting-fact F1 (directly transferable to
  "did the note cite the right edges").
- **Trajectory eval** ("did it traverse vs. guess") — **AgenticRAGTracer**
  ([arXiv:2602.19127](https://arxiv.org/html/2602.19127v1)) grades the reasoning
  trajectory, not just the answer. `provenance.jsonl` already records the path
  (g11/g12/g13 hit the bridge), so a note naming the bridge with no ledger entry
  traversing it = a guess and should fail.
- **GraphRAG-specific** — GraphRAG-Bench
  ([arXiv:2506.02404](https://arxiv.org/pdf/2506.02404), ICLR'26); and
  [Beyond RAG for CTI](https://arxiv.org/html/2604.11419) is the same HRAG/AGRAG
  paper already cited in [best-practice-architecture.md](./best-practice-architecture.md)
  — retrieval and eval research converge on it.

**Planted-needle design** against the fixture: encode the bridge as
`{answer: "Halberd↔Wren co-location", required_path: [MEMBER_OF, CO_LOCATED,
CO_LOCATED], required_cites: [...]}`, then score each run on (1) recall (surfaced
it?), (2) trajectory (provenance actually traversed the path?), (3) precision
(bridge facts cited to the right queries?), (4) pivot-burden proxy (hop/query
count to reach it).

---

## Decisions this pass produces

- [x] **Citation gate v2 Stage 1** — uncited-claim detection (recall). Shipped
      2026-06-02. `# research(2026-06): ALCE citation recall.`
- [ ] **Citation gate v2 Stage 2** — entailment (precision) via HHEM-2.1-Open
      (hermetic) + key-gated frontier variant; validate on hedged claims first.
- [x] **Tradecraft lint** ✅ SHIPPED (2026-06-02) — `provenance/tradecraft.py`
      `lint_estimative_language`: flags non-standard estimative hedges, maps used
      WEP terms to their ICD-203 band, detects the analytic-confidence axis.
      Advisory `tradecraft.json` artifact. *Remaining:* LLM-RUBRIC scoring; have
      the `entity-workup` skill prompt the agent to use WEP terms + state
      confidence (the real note currently uses neither).
- [x] **Phase 4 eval harness** ✅ SHIPPED (2026-06-02) — `evaluation/needle.py`
      `score_workup` + `HALBERD_FIXTURE` + `ariadne eval <dir>`: scores recall,
      trajectory (traversed vs guessed), `grounded` (both), and pivot-burden
      against the planted Compound-Alpha needle. The real Phase-1 Halberd workup
      scores `grounded=True` (recall 1.0, trajectory 1.0, 14 queries). *Remaining:*
      per-edge supporting-fact F1; more fixtures.
- [ ] *(Bigger bet, optional)* ACH-structured `entity-workup` (AgentCDM).

## Key sources

- ALCE — [arXiv:2305.14627](https://arxiv.org/abs/2305.14627) (citation precision/recall)
- MiniCheck — [github/Liyan06/MiniCheck](https://github.com/Liyan06/MiniCheck) · AlignScore — [ACL 2023](https://aclanthology.org/2023.acl-long.634/) · LIM-RA — [arXiv:2404.06579](https://arxiv.org/html/2404.06579v1) · RAGAS faithfulness — [docs](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/) · FActScore — [EMNLP 2023](https://aclanthology.org/2023.emnlp-main.741/)
- ICD-203 — [fas.org PDF](https://fas.org/irp/dni/icd/icd-203.pdf) · estimative-uncertainty calibration — [arXiv:2405.15185](https://arxiv.org/pdf/2405.15185) · LLM-RUBRIC — [arXiv:2501.00274](https://arxiv.org/pdf/2501.00274) · AgentCDM — [arXiv:2508.11995](https://arxiv.org/pdf/2508.11995)
- MuSiQue — [arXiv:2108.00573](https://arxiv.org/abs/2108.00573) · AgenticRAGTracer — [arXiv:2602.19127](https://arxiv.org/html/2602.19127v1) · GraphRAG-Bench — [arXiv:2506.02404](https://arxiv.org/pdf/2506.02404)
