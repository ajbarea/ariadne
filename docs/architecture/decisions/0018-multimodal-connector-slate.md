# 0018, Multimodal connector slate — text / audio / relational shipped, video deferred

- **Status:** Accepted (2026-06-05)
- **Deciders:** Ariadne maintainers

## Context

To demonstrate Ariadne across heterogeneous data of different *kinds, shapes, and
sizes* — and to stress the dataset-agnostic adapter seam ([ADR-0006](0006-dataset-agnostic-pipeline.md))
— we add HuggingFace-backed dataset connectors beyond the synthetic seed. The goal
is breadth that proves the *sensemaking* thesis (entities, cross-source
reconciliation, provenance), not breadth for its own sake.

## Decision drivers

- **Entity-rich, on-purpose data.** A connector earns its place by exercising
  entities / relationships / cross-store reconciliation, not by checking a
  modality box.
- **Agentic-to-text ([ADR-0008](0008-multimodal-agentic-to-text-not-native-embeddings.md)).**
  Every modality is reasoned over as text, so a dataset that *ships* text
  (transcript / caption / description) proves a modality without a live ASR/VQA
  model.
- **Lean ingestion + auditable.** Prefer HF streaming (parquet) or cache-aware
  download; deterministic mapping (no LLM), like the enron transform.
- **Quality over checkbox.** A forced, mismatched dataset lowers project quality.

## Decision

Ship a four-kind slate, three connectors now:

| Kind | Connector | Source | Access |
| --- | --- | --- | --- |
| Documents (text) | `enron` | `corbt/enron-emails` | HF stream |
| Speech (audio) | `worldspeech` | `disco-eth/WorldSpeech` | HF stream (transcript; ADR-0008) |
| Relational (structured) | `lahman` | `NeuML/baseballdata` | HF cache-aware CSV download |

**Video is deferred, not dropped.** Surveying the most-downloaded HF video
datasets, the field is dominated by robotics manipulation (LeRobot / DROID /
bridge / fractal / behavior / RoboTwin / EBench), sign-language gesture sets, VLM
*training* corpora (LLaVA-OneVision), test/junk repos, and QA benchmarks
(MSR-VTT, Video-MME) — none entity-rich for intelligence sensemaking. MSR-VTT
(generic captioned clips) was explicitly rejected. Per ADR-0008, video would be a
fourth *modality* but the same *mechanism* WorldSpeech already proves
(non-text sensory → text → reason), so forcing a mismatched video set would lower
quality for no analytic gain.

**Landing criteria** (any video connector must meet all, so this is not a
forever-defer): (1) entity-rich — named people / orgs / events; (2) HF-streamable
or cache-aware-downloadable; (3) ships text annotations (transcript / caption /
description) so agentic-to-text needs no live model; (4) acceptable license. The
likely source is broadcast-news / hearing transcripts found via full-text search,
not the download charts.

## Consequences

- Three real connectors (text / audio / relational) exercise documents, speech,
  and a clean shared-key relational schema — covering distinct shapes and sizes
  and the entity-resolution path (ADR-0016).
- The adapter seam makes the video connector a drop-in when a dataset meets the
  criteria; no architecture change is owed.
- Honest framing: Ariadne is demonstrated multimodal (text + audio + relational)
  today; "video" is a documented, criteria-gated next step rather than a shipped
  box-check.

## Sources

- Enron / WorldSpeech / Lahman dataset cards on the HF Hub (linked from the
  adapters in `src/ariadne/datasets/`).
- HF "most downloads" video listing (2026-06): robotics / gesture / training /
  benchmark dominated — surveyed during selection.
