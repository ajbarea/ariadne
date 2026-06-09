# Overview

Ariadne is a sensemaking harness for entities that live inside large
organizations.

## The problem

Intelligence about a single entity is distributed across systems that were never
designed to interoperate:

- **graph databases** for relationships, hierarchy, and networks
- **relational stores** for records, attributes, and facts
- **unstructured repositories** for free text, documents, and transcripts

The content spans modalities too: metadata, text, imagery, and video. The barrier
isn't getting into any one store; it's reasoning across all of them at once. The
evidence linking two facts often exists only through an implicit organizational
relationship, sitting in a different store and format than either fact.

## The approach

Ariadne uses the **Claude Agent SDK** as a single analytic interface over these
systems. An orchestration layer dispatches specialized tools to retrieve,
interpret, and synthesize evidence across graph, relational, and unstructured
sources, without replacing the infrastructure underneath.

The research question: what tools, skills, and hooks does a harness need to
support a rigorous end-to-end analytic workflow over entities in an
organizational hierarchy? Ariadne prototypes the minimum viable set: database
connectors, modality processors (image and video analyzers, text extractors), and
hierarchical reasoning hooks.

## The deliverable

A working prototype that runs an end-to-end workflow. It takes a target entity or
organizational node as input, runs a coordinated sequence of tool calls, and
synthesizes the evidence into a cited analytic product.

It is judged on four things:

1. **Traverse** organizational relationships.
2. **Reconcile** evidence across modalities.
3. **Reduce** the analyst's manual-pivot burden.
4. **Surface** non-obvious connections that conventional tooling would miss.

## The umbrella role

Ariadne is an umbrella effort. Rather than duplicate work, it defines
integration interfaces so contributions from sibling projects (graph-extraction
pipelines, entity-resolution models, multimodal indexing) surface as callable
tools inside the harness. That makes it both a standalone research contribution
and a demonstration layer for the wider portfolio.

## Where to next

- [Get Started](getting-started.md): set up the toolchain and run the scaffold.
- [Best-Practice Architecture](research/best-practice-architecture.md): the
  research grounding the design.
- [Roadmap](roadmap.md): the phased build order.
