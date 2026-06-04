# Open-Weight Model Validation: Does the Air-Gap Seam Hold?

> **Provenance.** Run 2026-06-04 to validate [ADR-0012](../architecture/decisions/0012-cloud-vs-air-gapped-deployment-fork.md).
> ADR-0012 *decided* that the cloud/air-gapped deployment fork is a **single seam
> at the orchestrator model**; this is the experiment that turns that architectural
> claim into measured evidence. Everything here is a live run on this repo's code at
> the session HEAD — no code changed, only `ANTHROPIC_BASE_URL`. Serving config is
> committed at [`infra/litellm/`](https://github.com/ajbarea/ariadne/tree/main/infra/litellm).

## The question

ADR-0012 narrowed the brief's highest-leverage open question from *"how do we
air-gap Ariadne?"* to *"which open-weight model clears the eval bar?"* — because
the architecture already forks at one point and the retrieval/embedding/eval
layers are already local. This run answers the narrowed question on real hardware.

## What was held constant (so only the model varies)

| Variable | Value |
| --- | --- |
| Harness | Ariadne at session HEAD, **zero code change** |
| Task | `ariadne workup Halberd --dataset synthetic --sql` |
| Stores | Neo4j 5.26 + Postgres 17 (Colima), seeded synthetic org graph + personnel |
| Needle | planted Halberd↔Wren cross-modality tie (shared `cover_employer`) + Talon location conflict |
| Eval | `ariadne eval --fixture halberd --reconcile synthetic` (mechanical) + `ariadne rubric` (ICD-203, **judged by cloud Claude** for an independent strong grader) |
| Seam | `ANTHROPIC_BASE_URL` → LiteLLM `/v1/messages` → Ollama (Metal, native) |

The **only** thing that changes between rows is the model behind the proxy. That
is the entire point: if the seam holds, swapping the model is two env vars.

## The seam works (plumbing, proven first)

Before scoring quality, the translation path was validated end-to-end: an Anthropic
Messages API request carrying a tool definition round-tripped through LiteLLM to a
local Ollama worker and came back as a correct `tool_use` block
(`stop_reason: "tool_use"`). The Claude Agent SDK / `claude` CLI then drove a full
multi-turn workup against the local worker — `POST /v1/messages` (incl. the
`?beta=true` variant) returning `200 OK` throughout. **No Ariadne code is
model-aware; the fork is genuinely one env var.**

> Packaging note worth keeping: install Ollama via the **`ollama-app` cask**, not
> the `ollama` formula — the formula ships without the `llama-server` runner the
> current engine needs, and every `/v1/messages` call 500s with
> `llama-server binary not found` until you switch.

## Results

Scores are on the identical synthetic two-store workup. `grounded` = surfaced the
needle **and** the ledger shows the path was actually traversed (naming without
traversing is scored as a guess). Reconciliation credits a case only when the fact
is surfaced, written with explicit corroboration/conflict language, **and** both
stores were queried.

| Model | Params (active) | Evidence calls | grounded | recall | trajectory | reconciliation | citation gate | rubric (ICD-203) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **Claude (cloud baseline)** | frontier | 24 | ✅ True | 1.00 | 1.00 | 1.00 (2/2) | ✅ pass | ~4.50–4.75 / 5 |
| **qwen3:14b** _(MoE 30B-A3B was queued)_ | 14B | loop ran (multi-turn tool calls) | DNF¹ | — | — | — | — | not reached |
| **qwen3:0.6b** _(floor)_ | 0.6B | **0** | ❌ False | 0.00 | 0.00 | 0.00 (0/2) | ❌ fail | not scored |

¹ **DNF = throughput-bound, not a capability failure.** The 14B drove the agent
loop correctly (valid `tool_use`, turns 1–2 completed) but did not finish a scorable
note in practical time. Ollama's own timing shows why: each turn reprocessed a
**~30k-token, ever-growing context** (system prompt + skill + tool defs + every prior
tool result + qwen3's verbose thinking) at **~80 tok/s ≈ 5 min/turn** on an M1 Pro
(32 GB), against the 32k context ceiling. It is grinding, not stalled or unable to
reason. See the operating-envelope response below.

The 0.6b floor is informative: it never queried the stores, answered from nothing,
leaked raw `<thinking>` into the note, and the citation gate caught it. That is the
eval harness demonstrating **discriminating power** — an incapable model fails
every axis, so a passing score from a larger model is meaningful, not a rubber stamp.

## Findings

1. **The seam holds; the bottleneck is hardware throughput, not architecture.** A
   non-Claude model satisfies the harness's tool-use contract (proven), so "can
   local models run Ariadne?" is a *capability + throughput* question, not a lock-in
   one. On an M1 Pro the limiter is **prompt-processing of a large, accumulating
   context** (~5 min/turn), worsened by qwen3's thinking-mode token bloat.
2. **The fix is model-aware context discipline, not chunking-to-fit.** qwen3:14b
   supports 256k context — the issue is per-turn *cost*, not a hard limit. The levers
   Ariadne owns: cap tool-result verbosity (the largest growing component we
   control), `max_turns` + `max_thinking_tokens`, and serving-side thinking-off /
   KV-cache reuse. The SDK owns whole-conversation compaction and exposes no
   per-model context knob, so we do not hand-roll history re-chunking.
3. **This produced a design response, not just a number.** The user-selectable
   model-profiles design now carries a per-model **operating envelope** so a local
   profile runs lean and a frontier profile runs generous, from one codebase
   (see `docs/superpowers/specs/2026-06-04-user-model-selection-design.md`, D6).
4. **A scorable open-weight *quality* number needs a faster host.** The 14B/30B
   quality rows are a follow-up on a GPU host or hosted open-weight endpoint; the
   throughput wall on commodity Apple Silicon is itself a useful SCADS air-gap
   deployment finding (plan for inference hardware, not just model weights).

## What this validates for the brief

- ADR-0012's single-seam claim is **operationally true**, not just argued: the
  cloud→air-gap swap is `ANTHROPIC_BASE_URL` + a local Ollama worker, with the
  gates, provenance, and eval byte-identical across both deployments.
- The eval harness is the right instrument for the narrowed question — it fails a
  weak model cleanly, so it can certify a strong open-weight one.
