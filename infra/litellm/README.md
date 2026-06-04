# Air-gap serving seam (LiteLLM + Ollama)

This is the runnable form of [ADR-0012](../../docs/architecture/decisions/0012-cloud-vs-air-gapped-deployment-fork.md):
the deployment fork is a **single seam at the orchestrator model**. Point
`ANTHROPIC_BASE_URL` at a LiteLLM proxy that translates the Anthropic Messages
API to a local open-weight worker, and the entire Ariadne harness — agent loop,
MCP tools, skills, provenance hook, citation gate, eval — runs unchanged. No
Ariadne code is model-aware.

```
 ariadne workup ──> claude CLI ──ANTHROPIC_BASE_URL──> LiteLLM :4000 ──> Ollama :11434
 (Agent SDK)        (Anthropic Messages API)           /v1/messages       open-weight model
```

## Why this shape (research, 2026-06)

- **LiteLLM** exposes `/v1/messages` natively and is the recommended
  Anthropic↔local translation gateway (`docs.litellm.ai/docs/anthropic_unified`).
- **`ollama_chat/`** (not `ollama/`) routes through Ollama's `/api/chat`, which
  carries tool calls — required for Ariadne's MCP tool loop.
- **Ollama native on macOS** uses Metal directly. A containerised vLLM under
  Colima would be CPU-only (Apple Silicon can't pass Metal into Docker), so the
  worker runs on the host, the stores run in Colima.
- Install Ollama via the **`ollama-app` cask**, not the `ollama` formula — the
  formula ships without the `llama-server` runner the current engine needs.

## Run it

```bash
# 1. Local model worker (Metal). 32 GiB M1 Pro fits qwen3:30b (A3B MoE, ~19 GB)
#    or, more comfortably, qwen3:14b (~9 GB).
brew install --cask ollama-app
OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 OLLAMA_CONTEXT_LENGTH=32768 ollama serve &
ollama pull qwen3:30b          # edit config.yaml to match the tag you pull

# 2. Translation proxy (isolated; never touches Ariadne's deps)
uv tool install 'litellm[proxy]'
litellm --config infra/litellm/config.yaml --port 4000 &

# 3. Stores
docker compose -f infra/neo4j/docker-compose.yml up -d
docker compose -f infra/postgres/docker-compose.yml up -d
docker exec -i ariadne-neo4j cypher-shell -u neo4j -p password < infra/neo4j/seed.cypher

# 4. Drive the harness against the local model — ZERO code change, just two env vars
ANTHROPIC_BASE_URL=http://localhost:4000 ANTHROPIC_API_KEY=local-no-key \
  ariadne workup Halberd --dataset synthetic --sql --out /tmp/ow

# 5. Score it exactly as for the cloud model
ariadne rubric /tmp/ow/halberd
ariadne eval   /tmp/ow/halberd --fixture halberd --reconcile synthetic
```

`ANTHROPIC_API_KEY` only needs to be non-empty (the local proxy ignores it);
`python-dotenv` loads with `override=False`, so these exported vars win over any
`.env`. See [`docs/research/open-weight-validation.md`](../../docs/research/open-weight-validation.md)
for measured results.
