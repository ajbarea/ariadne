# Requirements & Priorities

This is Ariadne's prioritization made explicit: every requirement traced to a
**stakeholder need** (a brief success criterion or design constraint), the
**metric** that proves it, its **priority tier** with rationale, and its
**feasibility/status**. It answers the SCADS *Sense & Orient* worksheet's step 7
("Prioritization of Requirements") and feeds steps 2/6 (metric framing and
goal→metric mapping) and step 8 (sensing back-brief).

The stakeholder needs are the brief's own, recorded in the
[charter](https://github.com/ajbarea/ariadne/blob/main/ROADMAP.md):

- **SC1: Traverse** organizational relationships.
- **SC2: Reconcile** information across modalities.
- **SC3: Reduce** the analyst's manual pivot burden.
- **SC4: Surface non-obvious** connections impractical to find by hand.
- **C-spec: Specification & validation** ("how do you know what works?"), the
  brief's stated *core* challenge.
- **C-gov: Governance** uniform across quality, security, and data integrity.

## How we prioritize (the rule)

1. **P0: Demonstrable value.** The four success criteria define what "works"
   *means*. Each must be provable by a metric on a planted-needle fixture. Nothing
   ranks above proving SC1-SC4.
2. **P1: The validation spine.** The brief's *core* challenge is C-spec, not the
   features themselves: an unvalidated P0 is worthless because no one can trust it.
   So the gates and eval harness that certify P0, and the governance that makes
   them safe (C-gov), sit immediately below P0, above any expansion.
3. **P2: Generalization & deployment.** Proving the harness transfers beyond one
   synthetic graph (the *secondary* deliverable) and runs in the brief's required
   deployments. Valuable, but only once P0/P1 hold.
4. **P3: Stretch / deferred.** Real but YAGNI-gated until a use case demands them.

Feasibility is rated against the current toolset; most P0/P1 are already shipped,
which is why they are P0/P1 and not aspirations.

## P0: Demonstrable value (the four success criteria)

| Requirement | Serves | Metric (proof) | Feasibility | Status |
|---|---|---|---|---|
| Multi-hop graph traversal across the org hierarchy | SC1 | `trajectory` + `grounded` (ledger shows the path was walked, not guessed) | Shipped (Neo4j connector) | ✅ |
| Cross-modality reconciliation (corroborate / flag conflict) | SC2 | `reconciliation` (corroboration + conflict cues, both stores queried), `sf_f1` | Shipped (graph+relational+text) | ✅ |
| Lower manual pivot burden via one analytic interface | SC3 | `pivot_burden` (queries/hops in a single agent loop) | Shipped | ✅ |
| Surface planted non-obvious links | SC4 | needle `recall` + `grounded` on Halberd↔Wren and kaminski-aol fixtures | Shipped | ✅ |

## P1: The validation spine (C-spec + C-gov)

| Requirement | Serves | Metric (proof) | Feasibility | Status |
|---|---|---|---|---|
| No-fabrication + no-uncited-claim citation gate | C-spec | citation report `dangling`/`uncited`/`unsupported` = 0 | Shipped | ✅ |
| Factual-precision check (entailment) | C-spec | HHEM `unsupported` on non-estimative claims | Shipped (`eval` extra) | ✅ |
| Analytic calibration (ICD-203/206 tradecraft) | C-spec, C-gov (quality) | tradecraft lint: estimative-band + confidence presence | Shipped | ✅ |
| Analytic-standards rubric (the axes gates can't see) | C-spec | ICD-203 rubric overall + per-criterion (judged independently) | Shipped (`rubric` extra) | ✅ |
| Planted-needle eval harness with discriminating power | C-spec | grounded/recall/trajectory; proven to fail a weak model cleanly | Shipped | ✅ |
| Read-only governance audit over the ledger | C-gov (security/integrity) | `governance.json` write-verb violations = 0 | Shipped | ✅ |
| Per-product model + egress audit | C-gov (security) | profile name + egress class in `governance.json` + OTel | Shipped (ADR-0013) | ✅ |
| Uniform observability (GenAI OTel) | C-spec, C-gov | spans/metrics on every workup | Shipped (`otel` extra) | ✅ |

## P2: Generalization & deployment (secondary deliverable + deployment constraint)

| Requirement | Serves | Metric / proof | Feasibility | Status |
|---|---|---|---|---|
| Dataset-agnostic pipeline (write one adapter) | Secondary | Enron adapter runs the same workup+eval unchanged | Shipped (ADR-0006) | ✅ |
| Hybrid retrieval (full-text + vector, RRF) | SC4, secondary | semantic leg surfaces text-only needles | Shipped (ADR-0007) | ✅ |
| Cloud ↔ air-gapped on one codebase | Deployment constraint | open-weight model clears the eval bar via the single seam | Validating (ADR-0012) | 🟡 |
| User-selectable model profiles (governed) | Usability + C-gov | unknown profile rejected; air-gap omits cloud profiles | Shipped (ADR-0013) | ✅ |
| Distribution as MCP server + plugin | Adoption | installs and runs from any MCP client | Shipped (ADR-0009) | ✅ |

## P3: Stretch / deferred (YAGNI-gated)

| Requirement | Serves | Why deferred | Status |
|---|---|---|---|
| Subagent fan-out (parallel per-source workers) | scale | shared-context reconciliation + provenance redesign; ~15× tokens for a 2-store slice already scoring grounded | Deferred (ADR-0005) |
| Multi-player shared sessions | stretch goal | no validated single-player value gap yet | Deferred |
| Native multimodal embeddings | SC2 (media) | API-only breaks the air-gap and is an uncitable black box | Rejected (ADR-0008) |
| Network egress *enforcement* | C-gov | curation suffices pre-deploy; enforcement is a deployment-time control | Deferred |

## What this exposes

- **P0 and P1 are essentially complete.** The demonstrable-value criteria all have
  passing metrics, and the validation spine that certifies them is shipped. That is
  the deliberate over-investment in C-spec the brief asks for.
- **The live edge is P2 deployment validation** (ADR-0012: which open-weight model
  clears the eval bar), exactly where current work sits.
- **Nothing in P0/P1 is blocked.** The one remaining blocked item (licensed Avocado
  data) is P2 and gated on data access, not on engineering. The PyPI publish has shipped
  (`ariadne-sensemaking`).
