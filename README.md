# memora-mcp

Persistent, automatic memory for a **meta-harness** — one memory shared across every agent it runs. Backed by [Microsoft Memora](https://github.com/microsoft/Memora)'s harmonic memory and wired into [Omnigent](https://github.com/omnigent-ai/omnigent) through standard hooks.

Work through any agent; the durable facts you establish are captured on their own and surface in later sessions — in *any* agent — recalled by meaning, not keyword. It runs on the model plane you already have (your Claude/Codex subscription by default) and needs no API key and no services.

> **Want the full picture first?** [**docs/OVERVIEW.md**](docs/OVERVIEW.md) explains what Omnigent and Memora each are, why Memora's memory is measurably better (with Microsoft's benchmarks), how we adapt it, and why we combine them this way. This README is the setup-and-use reference.

## What you get

- **Automatic capture.** When a session ends or compacts, an Omnigent hook quietly distills the durable facts — decisions, config discoveries, failures and fixes, preferences, conventions — with no "save" step.
- **Automatic recall.** Every new session opens with the memories relevant to *that* project already in context, ranked by relevance, framed as reference.
- **Shared across agents.** A fact learned in Codex surfaces in Claude Code tomorrow. One store, every harness.
- **Free to run.** Extraction uses a cheap model on your subscription; retrieval uses an in-process embedder. No key, no daemon, no metered service by default.
- **Yours to manage.** List, trace, and forget any memory from the CLI; import your existing Claude Code memories in one command.

## Quick start

```sh
curl -fsSL https://raw.githubusercontent.com/trwilcoxson/memora-mcp/main/install.sh | sh
```

One command: clones a pinned Memora checkout, builds a venv under `~/.memora-mcp/` (torch + chromadb, a few GB), **detects your model plane** (a logged-in `claude`/`codex` subscription — no key needed), registers the memory tools at Claude Code user scope, **turns automatic memory on**, and runs a health check. If you have Omnigent, it detects that too — memory then works in every `omni claude` session automatically. Idempotent; re-runs take seconds.

That's it. Just work — in `claude` or `omni claude` — and memory accumulates and surfaces on its own.

Flags: `--backend openai` (use an API key instead of a subscription), `--no-register`, `--pin <memora-ref>`. Check health any time with `memora-mcp doctor`.

<details>
<summary>Manual install</summary>

Memora publishes no package, so you need a checkout of it plus this repo:

```sh
git clone https://github.com/microsoft/Memora ~/.memora-mcp/Memora
uv venv --python 3.12 ~/.memora-mcp/venv
~/.memora-mcp/venv/bin/pip install -r ~/.memora-mcp/Memora/requirements.txt
~/.memora-mcp/venv/bin/pip install memora-mcp    # or -e /path/to/memora-mcp
~/.memora-mcp/venv/bin/memora-mcp enable          # turn on automatic memory
```

The server finds Memora automatically at `~/.memora-mcp/Memora/src`, or set `MEMORA_SRC=/path/to/Memora/src`.
</details>

## How it works

Four stages, all automatic, all fail-open (a failure means "no memory this turn," never a blocked session):

| Stage | What happens |
|---|---|
| **Capture** | Omnigent's `Stop` / `PreCompact` hooks spool the new transcript span. Runs in the background; never blocks your session. |
| **Distill** | One turn on a cheap model extracts durable facts + cue anchors + a session summary. Secrets are scrubbed first. |
| **Store** | Facts go into Memora's harmonic store (abstraction + cues + full value); near-duplicates merge instead of piling up. |
| **Recall** | The next session opens with the memories most relevant to that project injected into context, scoped and framed as reference. |

The full rationale — and why Memora's representation makes "store more, trust recall" safe — is in [docs/OVERVIEW.md](docs/OVERVIEW.md).

## Bring your existing Claude memories

If you already use Claude Code's memory, import all of it into Memora so it's usable across every harness:

```sh
memora-mcp import-claude --dry-run   # preview
memora-mcp import-claude             # import (idempotent; re-run for new ones)
```

Faithful and free — Claude memories are already curated (their description becomes the abstraction, the name becomes cue anchors, the body is the value), so no model calls are needed. Secrets are scrubbed; cross-cutting notes go to user scope, per-project notes to their project.

## Manage it

```sh
memora-mcp list                # what it remembers
memora-mcp why   <id>          # where a memory came from (which agent, session, project)
memora-mcp show  <id>          # the full record
memora-mcp forget <id>         # delete + tombstone (won't be re-learned)
memora-mcp stats               # store + capture health
memora-mcp config              # the active configuration
memora-mcp enable / disable    # turn automatic memory on / off
```

## Tools (what agents call)

The MCP server also exposes memory as tools an agent can use directly:

| Tool | What it does |
|---|---|
| `memory_search(query, top_k)` | Semantic search; returns matching memories with scores |
| `memory_save(content, kind)` | Deliberately store a fact (automatic capture already does this for you) |
| `memory_get(key)` | Fetch one memory's full record |
| `memory_forget(key)` | Delete a memory |
| `memory_list(limit)` | List stored memories |

## What's different

- **Automatic, across a meta-harness.** Not a per-tool memory you save into by hand — capture and recall happen on their own, and one store serves every agent Omnigent runs.
- **Rides your instrumentation; adds nothing.** Memory uses the same plane that already runs your agents (your subscription by default) and provisions no new account, key, or service. Embeddings run in-process.
- **Economical on purpose.** Extraction is a read-and-structure task, so the default is a cheap model at low reasoning — validated good-enough against a larger model on a hard transcript. Recall costs nothing (embedding-only).
- **Memora's representation, adapted.** We keep Memora's harmonic store and retrieval — the benchmark-winning part — and replace only its conversational extractor with one tuned for coding work and your plane. See [docs/OVERVIEW.md](docs/OVERVIEW.md#what-we-use-from-memora-and-what-we-replaced).
- **Store more, trust recall.** Because Memora never embeds the raw value, a fuller store doesn't blur retrieval — so capture is generous and recall does the ranking, including ranking the opening context block by relevance to the current project.

## Configuration

Everything is an environment variable; `memora-mcp config` prints the resolved values. Defaults are chosen to be free-to-run and generous.

| Variable | Default | What it does |
|---|---|---|
| `MEMORA_PLANE` | `auto` | Force the model plane: `subscription-claude`, `subscription-codex`, `api`, or auto-detect. |
| `MEMORA_LLM_MODEL` | cheap per plane | Extraction model — `haiku` (Claude) / `gpt-4.1-mini` (API). Set `sonnet`, `gpt-5`, etc. for sharper memories. |
| `MEMORA_REASONING` | `low` | Reasoning/effort for extraction. `low` is plenty for this task. |
| `MEMORA_CAPTURE` | `rich` | How much to store: `lean` · `balanced` · `rich` (store more, trust recall). |
| `MEMORA_SESSION_SUMMARY` | `1` | Also store a short episodic summary of each session. |
| `MEMORA_EMBEDDING` | `local` | `local` (in-process, no key) or `api` (a served endpoint you opt into). |
| `MEMORA_MAX_DISTILLS_PER_DAY` | `300` | Write-cap safety valve. |
| `MEMORA_MIN_TURNS` | `3` | Skip capturing sessions shorter than this. |
| `MEMORA_MCP_HOME` | `~/.memora-mcp` | Store + config location. |
| `MEMORA_MCP_USER` | `$USER` | Selects the per-user collection. |

### Using an API or gateway instead of a subscription

```sh
export OPENAI_API_KEY=sk-...            # or a gateway key
export OPENAI_BASE_URL=https://...      # OpenAI, Azure, LiteLLM, vLLM, Databricks AI Gateway
export MEMORA_PLANE=api MEMORA_LLM_MODEL=gpt-4.1-mini
```

Embeddings stay in-process unless you also set `MEMORA_EMBEDDING=api`.

## Wiring (beyond the installer)

**Under Omnigent** — nothing extra. Omnigent launches native Claude sessions without `--strict-mcp-config`, so the user-scope registration the installer creates loads in every `omni claude` session. If you don't run with permissions bypassed, add `mcp__memora__*` to `permissions.allow` in `~/.claude/settings.json` (Omnigent routes native permission prompts to its web UI, which would stall an unattended session). Bonus: Omnigent's transcript forwarder logs every memory tool call into its conversation store, and its policy engine can gate them like any other tool.

**Plain Claude Code** — the installer already registers it. To do it by hand: `claude mcp add --scope user memora -- ~/.memora-mcp/venv/bin/memora-mcp`, then `memora-mcp enable` for automatic capture/recall.

**An Omnigent agent bundle** — declare the server inline (see `examples/omnigent-bundle/config.yaml`). Put any backend settings in the tool's `env` block, since the MCP subprocess is spawned by the Omnigent server, not your shell. Each sub-agent has its own tool surface, so declare it in every agent that should have memory.

**Verify the loop** — `python scripts/demo_roundtrip.py` saves a fact through the real server and retrieves it from a fresh process with a keyword-free paraphrase; exits non-zero if recall fails.

## Notes and limitations

- **Capture is background and asynchronous** — it never blocks a session, but a distilled memory shows up in your *next* session, not mid-turn. Recall (search + injection) is embedding-only and fast.
- **Scoping** is per-project (via a local sidecar registry) within a per-user collection. Memories are stamped with their project and provenance; the opening block is ranked by relevance to the current project.
- **One writer per store.** Chroma's `PersistentClient` isn't safe for concurrent writers across processes; capture is serialized with a lock. Very heavy concurrent multi-session writing is the one thing to avoid (or move Memora to a Redis backend).
- **Local-embedding recall** is strong on close paraphrases and weaker on far conceptual leaps; point `MEMORA_EMBEDDING` at a served endpoint if you want maximum recall precision.
- **Recalled memories are reference material, not instructions** — the injection frames them that way, and you should too if you build on this.

## Upstream findings

Issues in Memora (commit `dec3f8f`, 2026) found while building this, worth upstream fixes — we work around each at our layer rather than forking:

1. `query()` in the default cue-index mode returns nothing when the cue leg has no hits — the fusion step only runs `if primary_results and cue_results`, discarding primary hits (`core/memory.py`). We retry `PRIMARY_ONLY` on empty results.
2. `add(metadata=...)` is accepted but never persisted — the builder path drops caller metadata (so we keep scope/provenance in our own sidecar).
3. `PRIMARY_ONLY`/`CUE_ONLY` query modes overwrite the caller's `where` filter instead of AND-ing with it.
4. The non-Azure OpenAI clients don't accept an explicit `base_url` (`utils/llm.py`, `utils/embedding.py`); only the `OPENAI_BASE_URL` env fallback reaches a gateway.
5. `torch`/`transformers` import eagerly even for pure-OpenAI use, and the documented `pip install -e .` can't work (no `pyproject.toml`).

## License

MIT. Memora is Microsoft's (MIT-licensed) and Omnigent is Databricks' (open source); this project is an independent integration, not affiliated with either.
