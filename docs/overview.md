# Overview

Ariadne is a **sensemaking harness for nonatomic entities** — SCADS Project #1.

## The problem

Modern collection environments produce intelligence about entities embedded
within large, complex organizational hierarchies, stored across highly
heterogeneous systems. Relevant information about a single entity or
relationship may be distributed across:

- **graph databases** — relationships, hierarchy, networks
- **structured / relational stores** — records, attributes, facts
- **unstructured repositories** — free text, documents, transcripts

…while the associated content spans **multiple modalities**: metadata records,
free text, imagery, and video. No single query interface or analytic tool
addresses this full spectrum. Analysts are forced to pivot manually across
disparate systems, losing context and analytic momentum at every transition.

The challenge is not merely data access — it is **coherent, multi-hop reasoning
across heterogeneous representations**, where critical evidence may be linked
only through implicit organizational relationships buried across modalities.

## The approach

Ariadne leverages an agentic AI harness — the **Claude Agent SDK** — as a
*unifying analytic interface* over these diverse data environments. Rather than
replacing existing data infrastructure, the harness serves as an **orchestration
layer**: it dispatches specialized tools and skills to retrieve, interpret, and
synthesize information across graph, structured, and unstructured sources in a
coordinated workflow.

**Central research question:** given such a harness and its user interface, what
specific **tools, skills, and hooks** are necessary to support a rigorous
end-to-end analytic workflow targeting entities within an organizational
hierarchy? Ariadne identifies and prototypes the **minimum viable toolset** —
database connectors, modality-specific processors (image/video analyzers, NLP
extractors), and hierarchical reasoning hooks — required to demonstrate
meaningful analytic value.

## The deliverable

A working prototype that demonstrates an end-to-end analytic workflow within the
harness. The prototype takes a **target entity or organizational node** as input
and, through a coordinated sequence of tool invocations, surfaces relevant
evidence from across all available data structures and modalities, synthesizing
findings into a coherent analytic product.

Success is evaluated on the harness's ability to:

1. **traverse** organizational relationships,
2. **reconcile** information across modalities,
3. **reduce** the analyst's manual-pivot burden, and
4. **surface non-obvious connections** impractical to discover through
   conventional tooling.

## SCADS umbrella role

Ariadne is an **umbrella effort** within the SCADS program, designed to
incorporate and build upon datasets, tools, and analytic insights from sibling
projects. Rather than duplicating work, it defines **integration interfaces**
that let contributions from other SCADS projects — graph-extraction pipelines,
entity-resolution models, multimodal indexing schemes — be surfaced as callable
tools within the harness. This positions Ariadne both as a standalone research
contribution and as a unifying demonstration layer for the SCADS portfolio.

## Where to next

- [Getting Started](getting-started.md) — set up the toolchain and run the scaffold.
- [Best-Practice Architecture](research/best-practice-architecture.md) — the
  June-2026 research grounding the design.
- [Roadmap](roadmap.md) — the phased build order.
