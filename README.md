# memora-mcp

An [MCP](https://modelcontextprotocol.io) server that gives a *meta-harness* one persistent, semantic memory shared across every agent it runs — backed by [Microsoft Memora](https://github.com/microsoft/Memora) and wired into [Omnigent](https://github.com/omnigent-ai/omnigent).

Establish a fact while working through one agent; recall it by meaning in any later session, in any other agent. Automatic capture, automatic recall, running on the model plane you already have.

> **New here?** Read **[docs/OVERVIEW.md](docs/OVERVIEW.md)** — what Omnigent and Memora each are, why Memora's memory architecture is measurably better (with Microsoft's benchmarks), and why we bring them together this way. This README is the install-and-use reference.

```
session A (Codex):
  memory_save("We pinned the Stripe API version to 2026-05-28 because the June
               release changed webhook signature ordering and broke replay tests.")

session B (Claude Code, days later):
  memory_search("why is our billing provider locked to an older release?")
  -> Payments Service Stripe API Version Pinning (score 0.53): The payments
     service's Stripe API version was pinned to 2026-05-28 because the June
     release changed webhook signature ordering and broke replay tests.
```

The query shares no keywords with the saved text. That is the point: Memora stores each memory as a full value plus a one-sentence abstraction plus short "cue" anchors, and only the abstractions and cues are embedded and searched. Matching is by meaning; the full value comes back on a hit. Near-duplicate saves are merged into the existing memory instead of piling up.

## Tools

| Tool | What it does |
|---|---|
| `memory_save(content, kind)` | Distill `content` into indexed memories (`kind`: `note` or `conversation`) |
| `memory_search(query, top_k)` | Semantic search; returns matching memories with scores |
| `memory_get(key)` | Fetch one memory's full record by index key |
| `memory_forget(key)` | Delete a memory |
| `memory_list(limit)` | List stored memories |

## Quick start

```sh
curl -fsSL https://raw.githubusercontent.com/trwilcoxson/memora-mcp/main/install.sh | sh
```

One command: clones a pinned Memora checkout, builds a venv under `~/.memora-mcp/` (torch + chromadb, a few GB), picks a backend (`OPENAI_API_KEY` if exported, otherwise local Ollama — pulling a small chat model and an embedding model if needed), registers the server at Claude Code user scope, and runs `memora-mcp doctor` to verify the whole chain. Idempotent — re-run any time; re-runs take seconds.

Then open a new `claude` or `omni claude` session and say "save to memory: …". In a later session, "search memory for …" finds it by meaning.

Flags: `--backend ollama|openai`, `--no-register`, `--pin <memora-ref>`. Health check any time:

```sh
~/.memora-mcp/venv/bin/memora-mcp doctor
```

<details>
<summary>Manual install</summary>

Memora publishes no package, so you need a checkout of it plus this repo:

```sh
git clone https://github.com/microsoft/Memora
cd Memora
uv venv --python 3.12
uv pip install -r requirements.txt        # heavy: torch, transformers, chromadb
uv pip install memora-mcp                  # or: uv pip install -e /path/to/memora-mcp
```

The server needs `import memora` to resolve. Either add `Memora/src` to the interpreter path (a `.pth` file in `site-packages`), or set `MEMORA_SRC=/path/to/Memora/src`, or place the checkout at `~/.memora-mcp/Memora` (searched automatically).
</details>

## Configuration

Memory is **free to run by default**: extraction uses a cheap model on the plane you already have (your `claude`/`codex` subscription — no API key), and retrieval uses an in-process embedder (no key, no service). Everything is an environment variable; run `memora-mcp config` to see the resolved values.

| Variable | Default | What it does |
|---|---|---|
| `MEMORA_PLANE` | `auto` | Force the model plane: `subscription-claude`, `subscription-codex`, `api`, or auto-detect. |
| `MEMORA_LLM_MODEL` | cheap per plane | Extraction model — `haiku` (Claude) / `gpt-4.1-mini` (API). Set `sonnet`, `gpt-5`, etc. for sharper memories. |
| `MEMORA_REASONING` | `low` | Reasoning/effort for extraction. `low` is plenty for this task. |
| `MEMORA_CAPTURE` | `rich` | How much to store: `lean` · `balanced` · `rich` (store more, trust recall). |
| `MEMORA_SESSION_SUMMARY` | `1` | Also store a short episodic summary of each session. |
| `MEMORA_EMBEDDING` | `local` | `local` (in-process, no key) or `api` (a served endpoint you opt into). |
| `MEMORA_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model when `MEMORA_EMBEDDING=api`. |
| `MEMORA_MAX_DISTILLS_PER_DAY` | `300` | Write-cap safety valve. |
| `MEMORA_MIN_TURNS` | `3` | Skip capturing sessions shorter than this. |
| `MEMORA_MCP_HOME` | `~/.memora-mcp` | Store + config location. |
| `MEMORA_MCP_USER` | `$USER` | Selects the per-user collection. |

**Why these defaults:** extraction is a read-and-structure task, so a cheap model at low reasoning is more than good enough — on a hard test transcript, `haiku` caught every fact a larger model did. And because Memora never embeds the raw value (only compact abstractions and cues), storing more doesn't blur retrieval — so capture is generous by default and recall does the ranking. See [docs/OVERVIEW.md](docs/OVERVIEW.md) for the full rationale.

### Using an API or gateway instead of a subscription

```sh
# any OpenAI-compatible endpoint; extraction + (optional) embeddings run there
export OPENAI_API_KEY=sk-...            # or a gateway key
export OPENAI_BASE_URL=https://...      # OpenAI, Azure, LiteLLM, vLLM, Databricks AI Gateway
export MEMORA_PLANE=api MEMORA_LLM_MODEL=gpt-4.1-mini
```

Embeddings stay in-process unless you set `MEMORA_EMBEDDING=api`.

## Wiring

**Claude Code**

```sh
claude mcp add memora -- memora-mcp
```

or drop `examples/claude-code.mcp.json` into your project as `.mcp.json`. Pass the backend env either by exporting it before launching, or with `claude mcp add`'s `-e KEY=VALUE` flags.

**Omnigent bundle**

`examples/omnigent-bundle/config.yaml` is a complete agent with memory discipline in its prompt and the server declared as an inline MCP tool:

```yaml
tools:
  memora:
    type: mcp
    command: memora-mcp
    env:
      OPENAI_API_TYPE: openai
      ...
```

Run it with `omni run examples/omnigent-bundle`. Put the backend settings in the `env` block — the MCP subprocess is spawned by the Omnigent server, not your shell, so exported variables may not reach it. Each sub-agent in a bundle has its own tool surface; declare the server in every agent that should have memory.

**Under Omnigent (native Claude harness)**

Nothing extra: Omnigent launches native Claude Code sessions with its own `--mcp-config` for the bridge server, without `--strict-mcp-config` — so the user-scope registration `install.sh` creates loads in every `omni claude` session too.

Add `mcp__memora__*` to `permissions.allow` in `~/.claude/settings.json` if you don't run with permissions bypassed — Omnigent routes native permission prompts to its web UI, which stalls unattended sessions.

Two useful properties fall out of Omnigent's architecture: its transcript forwarder persists every `memory_save`/`memory_search` call and result into the Omnigent conversation store (auditable at `/v1/sessions/{id}/items`), and its policy hooks evaluate memory tool calls like any other tool, so CEL policies can gate them.

**Verify the loop**

```sh
python scripts/demo_roundtrip.py
```

Saves a fact through the real MCP server, then retrieves it from a second, fresh server process with a paraphrase that shares no keywords. Exits non-zero if recall fails.

## Notes and limitations

- `memory_save` is synchronous and LLM-bound (extraction + cue generation + merge checks — a few model calls). Expect seconds on a hosted model, longer on local Ollama. Search is embedding-only and fast.
- Scoping is per-user only: `MEMORA_MCP_USER` maps to a physical Chroma collection. Finer scoping (per-project, per-session) isn't reachable without patching Memora — the builder path drops caller metadata, and its primary/cue query modes overwrite caller `where` filters.
- Chroma's `PersistentClient` is not safe for concurrent writers across processes. Each MCP client spawns its own server process, so avoid many sessions writing heavily at the same time, or switch Memora's backend to Redis Stack (`db_type: redis`). A single long-lived memory service is the right production shape; this server is deliberately the minimal proof.
- Recalled memories are reference material. If you inject them into agent context, frame them as data, not instructions.

## Upstream findings

Issues in Memora (commit `dec3f8f`, July 2026) found while building this, worth upstream fixes:

1. `query()` in the default cue-index mode returns nothing when the cue leg has no hits — the fusion step only runs `if primary_results and cue_results`, discarding primary hits (`core/memory.py`). This server retries with `PRIMARY_ONLY` on empty results to compensate.
2. `add(metadata=...)` is accepted but never persisted — the builder path doesn't forward caller metadata to the store upsert.
3. `PRIMARY_ONLY`/`CUE_ONLY` query modes overwrite the caller's `where` filter instead of AND-ing with it.
4. The non-Azure OpenAI clients don't accept an explicit `base_url` (`utils/llm.py`, `utils/embedding.py`); only the `OPENAI_BASE_URL` env fallback reaches a gateway.
5. `torch`/`transformers` import eagerly even for pure-OpenAI use, and the README's `pip install -e .` can't work (no `pyproject.toml`/`setup.py`).

## License

MIT. Memora is Microsoft's, MIT-licensed; this project just wraps it and is not affiliated with Microsoft or Databricks.
