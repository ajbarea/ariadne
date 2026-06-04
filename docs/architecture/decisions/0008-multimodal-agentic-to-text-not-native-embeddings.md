# 0008, Multimodal fusion via agentic-to-text, not native multimodal embeddings

- **Status:** Accepted (2026-06-03)
- **Deciders:** Ariadne maintainers
- **Relates to:** [ADR-0004](0004-postgres-over-redis-for-relational-store.md) (in-store, auditable evidence), [ADR-0007](0007-hybrid-retrieval-fulltext-first.md) (hybrid text retrieval)

## Context

Ariadne's roadmap includes multimodal evidence (imagery, video, audio), Phase 3.
In June 2026 Google released **Gemini Embedding 2**, its first *natively
multimodal* embedding model: text, images, video, audio, and documents mapped
into one unified vector space. It is a strong model and, by independent
round-ups, the leader for cross-modal similarity search. The question raised:
should Ariadne adopt a native multimodal embedding (Gemini Embedding 2, or the
open-ish Cohere Embed v4 / Jina v4) as its multimodal approach, rather than the
agentic *convert-to-structured-text* fusion the architecture research settled on?

This decision is about the **multimodal fusion strategy**. It does not change the
text semantic leg (ADR-0007), where the embedder is already injectable.

## Decision drivers

- **Provenance / auditability is the spine.** Every fact Ariadne surfaces must
  trace to a citable source; the brief's central challenge is validation and
  governance.
- **Air-gap / PII.** Some corpora (e.g. Avocado, LDC2015T03) are access-controlled
  PII; content must not leave the box (ADR-0004's in-Postgres consolidation, and
  the cloud-vs-air-gap fork).
- **Transparency over opacity.** Anthropic's guidance and the project's research
  favour agentic search over text over opaque vector similarity.
- Don't reject a genuinely strong model reflexively, weigh it on Ariadne's
  actual requirements.

## Considered options

### A. Agentic multimodal-to-text, then embed/search the text (chosen)

Convert imagery/video/audio to **structured, citable text** (VQA + summarization
/ ASR), then reason, full-text- and vector-search over it with the existing
hybrid leg (ADR-0007).

- **Pros:** the converted text is **human-readable, citable, and auditable**,
  it flows through the same provenance/citation gates as every other evidence
  source; runs with **open-weight, self-hostable** components, so it survives the
  air-gapped/PII fork; transparent (an analyst can read *why* a frame matched);
  research-grounded (DeepMEL Modal-Fuser, V-Retriever, align visual evidence
  into the text modality before fusion).
- **Cons:** an extra extraction step; conversion can lose signal a raw embedding
  would keep; quality depends on the VQA/ASR model.

### B. Native multimodal embedding, Gemini Embedding 2

One unified text+image+video+audio vector space; no conversion pipeline; the
multimodal-similarity leader.

- **Pros:** simplest cross-modal recall; no OCR/VQA pipeline; state-of-the-art on
  multimodal retrieval benchmarks; 3,072-dim with Matryoshka downscaling.
- **Cons (decisive for Ariadne):** **cloud-API-only**: Gemini API / Vertex AI,
  **no open weights, no self-hosted or on-device option**: so you would ship
  (possibly classified / PII) imagery, video, and audio to a Google API, which
  **breaks the air-gap and PII governance** the project requires. A multimodal
  vector is a **black box**: it yields similarity but **no citable, auditable,
  human-readable evidence**, so a matched frame can't be cited or governed the way
  the brief demands. Public Preview maturity.

### C. Open-weight native multimodal embedding (Cohere Embed v4 / Jina v4)

- **Pros:** multimodal vectors without the Gemini cloud-only constraint (more
  self-hostable than Gemini Embedding 2).
- **Cons:** still produces uncitable black-box vectors (same auditability gap as
  B); heavier than the text leg; not needed for the MVP.

## Decision

**Adopt A.** Ariadne fuses multimodal evidence by converting it to **structured,
citable text** and reasoning/searching over that text, *not* by embedding raw
media into a shared vector space. Gemini Embedding 2 is the multimodal-similarity
leader, but it is the **wrong fit for auditable, air-gappable sensemaking**:
cloud-API-only (no air-gap) and uncitable (no provenance). The agentic-to-text
approach keeps every modality inside the same provenance, governance, and
hybrid-retrieval machinery already built.

**Left open (not rejected forever):** a native multimodal embedding could later
serve as an **optional, complementary cross-modal recall leg** (RRF-fused with
the text legs, via the same injectable-component pattern), but only an
**open-weight** one that satisfies the air-gap constraint, and only as a *recall
aid*, never as the system of record. The citable converted text remains the
evidence.

## Consequences

- Phase 3 builds a **multimodal-to-text extraction tool** (VQA/summarization/ASR,
  open-weight) whose output is citable Documents indexed by the B1/B3 hybrid leg,
  no new opaque vector space, no new cloud dependency.
- The air-gapped and PII forks stay viable for multimodal data.
- We forgo best-in-class raw multimodal-similarity recall; mitigated by extraction
  quality and the optional future open-weight recall leg above.

## Sources

- [Gemini Embedding 2 (Google blog)](https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-embedding-2/), natively multimodal, **cloud-API-only**, 3072-dim, public preview.
- [Gemini Embedding 2 paper](https://huggingface.co/papers/2605.27295)
- Best-practice architecture research (`docs/research/best-practice-architecture.md`), agentic multimodal-to-text fusion (DeepMEL, V-Retriever), adversarially verified.
- Multimodal embedding landscape 2026: [Milvus](https://milvus.io/blog/choose-embedding-model-rag-2026.md), [Mixpeek](https://mixpeek.com/curated-lists/best-embedding-models) (Cohere Embed v4 / Jina v4 as open-er multimodal options).
