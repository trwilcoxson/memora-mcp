# Cross-agent memory for the meta-harness

**What this is:** `memora-mcp` gives a *meta-harness* — one control plane running many different agents — a single persistent memory that every agent shares. A fact established while working through one agent is available to the next, automatically, without you re-explaining it and without standing up any new infrastructure.

It joins two existing systems:

- **[Omnigent](https://github.com/omnigent-ai/omnigent)** (Databricks, open source) — the meta-harness: one server that runs heterogeneous agents under a common layer of hooks, policy, and observation.
- **[Memora](https://github.com/microsoft/Memora)** (Microsoft Research) — a memory architecture that stores and retrieves by *meaning* rather than by keyword or raw embedding, and that Microsoft's own benchmarks show beats the common alternatives.

The thesis of this repo is narrow and specific: Omnigent already sees and can reach into every agent it runs, so it is the right place to put a memory — and Memora is the right memory to put there. This document explains both halves and why the combination is more than the sum.

---

## 1. The meta-harness: Omnigent

A harness is the runtime around an agent — the loop that feeds it a prompt, executes its tool calls, and streams back results. Different agents ship different harnesses: Claude Code, Codex, and Cursor each run as their own terminal application; headless SDK agents (the Claude Agent SDK, OpenAI Agents, Pi) run in-process; custom multi-agent orchestrators are their own thing again.

A **meta-harness** is a harness over harnesses. Omnigent runs all of the above as sessions under one server, behind one interface:

```
                        ┌─────────────────────────────────────────────┐
                        │                 Omnigent                     │
                        │   server · session store · hooks · policy    │
                        └─────────────────────────────────────────────┘
                            │        │        │        │        │
                   ┌────────┘   ┌────┘   ┌────┘   ┌────┘   └────────┐
                   ▼            ▼        ▼        ▼                 ▼
             ┌───────────┐ ┌────────┐ ┌────────┐ ┌────────┐  ┌──────────────┐
             │Claude Code│ │ Codex  │ │ Cursor │ │  Pi /  │  │  SDK agents  │
             │  (TUI)    │ │ (TUI)  │ │ (TUI)  │ │ Goose  │  │ custom bundles│
             └───────────┘ └────────┘ └────────┘ └────────┘  └──────────────┘
```

Why this matters, independent of memory:

- **No rough pivots between agents.** You don't context-switch tools when the task changes shape. Send the work to whichever agent fits — a terminal coding agent, a headless SDK agent, a custom orchestrator — from one place, without rewriting the workflow around it. The agent is a swappable detail; the meta-harness is the constant.
- **One governance layer.** Every tool call from every agent passes through a single policy engine (allow / deny / ask). Control is defined once, not reimplemented per agent.
- **Total visibility.** Each agent streams its full transcript — every message and tool call — back to the server. Nothing an agent does is invisible to the layer above it.

That third property is the one memory depends on. Because Omnigent already observes every agent and can already inject context into any session (through the hooks it installs), it is the natural home for a memory that serves *all* of them at once. There is exactly one place to capture from and one place to recall into, regardless of which agent is running.

---

## 2. The memory: Memora, and why it's better

Most agent memory today is one of two shapes, and both have a known failure mode:

- **Flat / RAG stores** embed the raw content and retrieve by vector similarity. Detail is preserved, but retrieval is fuzzy — you're matching against unstructured text — and the store fragments as related facts pile up as separate entries.
- **Graph / ontology stores** impose structure, but require predefined entities and relationships and are rigid to evolve.

Microsoft Research frames the underlying problem as an *unavoidable tradeoff between specificity and abstraction*: preserve fine-grained detail, or organize memory efficiently as it grows — pick one.

**Memora's harmonic memory representation resolves that tradeoff by separating what is stored from how it is organized and accessed.** Each memory entry has three parts:

```
   ┌──────────────────────── one memory entry ────────────────────────┐
   │                                                                   │
   │   PRIMARY ABSTRACTION  (indexed)   "payments Stripe rate limit"   │
   │        one short phrase — the canonical unit for updates          │
   │                                                                   │
   │   CUE ANCHORS  (indexed)   "429 reconciliation" · "25 req/s cap"  │
   │        several alternate semantic entry points to this memory     │
   │                                                                   │
   │   VALUE  (NOT indexed)                                            │
   │        "The payments service caps outbound Stripe calls at 25     │
   │         req/s per worker because above that Stripe returns 429s   │
   │         during the nightly reconciliation batch."                 │
   │        full detail, preserved, returned verbatim on a hit         │
   └───────────────────────────────────────────────────────────────────┘
```

Only the abstraction and the cue anchors are embedded and searched. **The value is never retrieved through its own content** — it's what comes back once a lightweight index entry matches. This is the whole trick, and it buys three things:

1. **Precise, controlled retrieval instead of fuzzy similarity.** You match against well-defined abstractions and cues, not raw text, so recall is guided rather than approximate — while the full, uncompressed detail is still what you get back.
2. **Many entry points to one memory.** The same fact is reachable through several cues. A query about the *symptom* ("why do we get 429s at night?"), the *component* ("staging redis port"), and the *value* ("how many requests per second?") all resolve to the same entry. This is where Microsoft reports the largest gains — multi-hop reasoning, via traversing cue anchors.
3. **Updates merge instead of duplicating.** Because the abstraction is the canonical unit, a new detail about an existing fact updates that entry rather than creating a near-duplicate. The store stays coherent as it grows — Microsoft reports Memora keeps roughly **half the entries per conversation that Mem0 does (344 vs. 651).**

Microsoft's reported results (their benchmarks, their numbers):

| | Memora | vs. |
|---|---|---|
| LoCoMo (LLM-judge accuracy) | **86.3%** | beats RAG, Mem0, Nemori, Zep, LangMem, and full-context inference |
| LongMemEval (LLM-judge accuracy) | **87.4%** | same field |
| Token consumption | **up to 98% lower** | vs. full-context inference |
| Entries stored per conversation | **344** | vs. 651 for Mem0 |

The point of pulling Memora in is not "add a vector database." It's that this specific representation — abstraction + cues + preserved value — is a measurably better way to remember, and it's the memory model we apply across every agent.

**A consequence we lean on: store more, trust recall.** Because the value is never embedded — only compact abstractions and cues are — a fuller store does *not* blur retrieval the way a fuller RAG index does. Storing a marginal memory costs a little space and nothing at query time; it just sits there until a query happens to want it. So the capture policy is deliberately generous by default (`MEMORA_CAPTURE=rich`): when the extractor is unsure whether something is worth keeping, it keeps it and lets Memora's retrieval rank. This is the opposite of the usual RAG instinct to filter hard, and it's justified precisely by the architecture above — the same property that gives Memora its benchmark lead is what makes "store more" safe.

> Sources: [Microsoft Research — *Memora: a harmonic memory representation*](https://www.microsoft.com/en-us/research/blog/memora-a-harmonic-memory-representation-balancing-abstraction-and-specificity/) and the [Memora repository](https://github.com/microsoft/Memora).

---

## 3. Why we bring them together, this way

The two systems fit because each supplies exactly what the other lacks:

- Omnigent has the **vantage point** — it sees every agent and can write into every session — but ships no real persistent memory.
- Memora has the **representation** — a superior way to store and recall — but is a library with no notion of *where the memories come from* or *which agent should see them*.

Put them together and memory stops being a feature attached to one tool. It becomes an **organ of the meta-harness**: one Memora store, written to and read from by every agent Omnigent runs, so Microsoft's memory architecture is now applied across *all* your agent contexts at once — not siloed inside whichever single agent happened to learn something.

```
   Claude Code   Codex   Cursor   Pi/Goose   SDK agents
        │          │        │         │           │
        └──────────┴────┬───┴─────────┴───────────┘
                        │   capture  (Omnigent hooks: on stop / pre-compact)
                        ▼
              ┌──────────────────────────────┐
              │   shared Memora memory        │   ← abstraction + cues + value
              │   (harmonic store, scoped     │      merged, deduped, per-project
              │    per project)               │
              └──────────────────────────────┘
                        │   recall  (Omnigent hook: on session start)
                        ▼
        every subsequent session, in any agent, opens already knowing
        ───────────────────────────────────────────────────────────
                        runs on your model plane
              your Claude / Codex subscription · or an API key /
              gateway if you prefer · embeddings in-process, no key
```

The load-bearing design decision — the one that makes this usable rather than another thing to operate — is that **memory rides whatever already instruments your agents, and adds nothing of its own.** A meta-harness user already has a way to run agents: a subscription, an API key, a gateway. Memory uses that same plane and provisions no new account, key, service, or daemon. On a subscription, distillation runs as a background agent turn on the plan you already pay for; embeddings run on a bundled on-device model. The default is your subscription precisely because that's what most people already have.

---

## 4. How it works

Four stages, all automatic, all fail-open (a failure degrades to "no memory this turn," never to a blocked session):

| Stage | Mechanism | Where |
|---|---|---|
| **Capture** | Omnigent's `Stop` / `PreCompact` hooks spool the new transcript span. No explicit "save." | user-scope Claude hooks (reach every Omnigent-managed session) |
| **Distill** | One background turn on a **cheap** model extracts facts + cue anchors + a session summary; secrets and noise are dropped first. | your plane, economical model (default `haiku`), low reasoning |
| **Store** | Facts are written through Memora's own store, preserving the abstraction + cue-row structure; near-duplicates merge. | Memora (local Chroma) |
| **Recall** | The next session opens with the relevant abstractions injected into context, scoped to the project, framed as reference-not-instruction. | Omnigent `SessionStart` hook |

### What we use from Memora, and what we replaced

We use Memora for the part that is genuinely novel and benchmark-proven — its **harmonic store and retrieval** (the abstraction + cue + value structure, semantic recall, cue-graph merge/dedup). We do *not* use Memora's own conversational extraction pipeline (`ChatMemoryBuilder`): its prompt is tuned for personal-assistant chat and ignores assistant turns, which is exactly backwards for coding agents where the assistant's reasoning is the valuable content — and it can only run against an OpenAI-shaped endpoint, which would break the no-key default. So the extractor is ours (one plane turn, domain-tuned, emits Memora-shaped ops), and the store underneath is Memora's, unchanged. This is a deliberate adaptation: Memora's *representation* is the crown jewel and we keep it intact; its *extractor* is replaced to fit the domain and the economics.

### Key properties

- **Economical by default.** The write path runs a cheap model at low reasoning — extraction is a read-and-structure task (find the durable facts, write an abstraction, emit cues), not a reasoning-heavy one, so it doesn't want frontier budget or premium subscription quota. Default is `haiku` on a Claude plan (a fraction of the quota), `gpt-4.1-mini` on an API plan. On a hard test transcript — a decision, a rejected alternative, a subtle failure→fix, an allowlisted IP, and a stated rule — haiku caught every fact with accurate cues; a larger model mostly just consolidated more. Step up to `sonnet` (`MEMORA_LLM_MODEL=sonnet`) for marginally crisper abstractions if you don't mind the quota; it's one setting.
- **The read path costs nothing.** Recall is embedding-only, and embeddings run on a bundled in-process model — no LLM call, no key, no service, per query. The only model spend is on capture, roughly once per session, in the background.
- **Model plane is detected, then configurable.** Logged-in `claude` / `codex` → your subscription (default, no key). `OPENAI_API_KEY` or a gateway → that. Force any choice with `MEMORA_PLANE` / `MEMORA_LLM_MODEL`. Nothing available → memory still stores and recalls; distillation waits until a plane exists.
- **Governed like everything else.** Because the memory tools are ordinary tool calls, Omnigent's policy engine gates them the same way it gates any other tool.
- **Scoped and inspectable.** Memories are stamped with their project and provenance (which agent learned them, in which session). You can list, trace (`why`), and `forget` any of them; a forgotten fact is tombstoned so it isn't silently re-learned.

### Configuration

Everything is an environment variable, set on the MCP server's `env` block or exported before launch. Run `memora-mcp config` to print the resolved values. The defaults are chosen to be free-to-run and generous:

| Variable | Default | What it does |
|---|---|---|
| `MEMORA_PLANE` | `auto` | Force the model plane: `subscription-claude`, `subscription-codex`, `api`, or auto-detect. |
| `MEMORA_LLM_MODEL` | cheap per plane | Extraction model. `haiku` (Claude) / `gpt-4.1-mini` (API) by default — set to anything you want. |
| `MEMORA_REASONING` | `low` | Reasoning/effort for extraction. Extraction rarely needs more than `low`. |
| `MEMORA_CAPTURE` | `rich` | How much to store: `lean` (only crystallized facts) · `balanced` · `rich` (store more, trust recall). |
| `MEMORA_SESSION_SUMMARY` | `on` | Also store a short episodic summary of each session. |
| `MEMORA_EMBEDDING` | `local` | `local` in-process (no key) or `api` (a served embedding endpoint you opt into). |
| `MEMORA_MAX_DISTILLS_PER_DAY` | `300` | Write-cap safety valve. |
| `MEMORA_MIN_TURNS` | `3` | Skip capturing sessions shorter than this. |

So the spectrum is yours: leave it entirely free (local embeddings + a cheap plane model), dial capture from `lean` to `rich`, or point the extractor at a stronger model when you want sharper memories and don't mind the cost.

---

## 5. Getting it running

The full setup is one command; see the [main README](../README.md) for details and options.

```sh
curl -fsSL https://raw.githubusercontent.com/trwilcoxson/memora-mcp/main/install.sh | sh
```

It provisions a pinned Memora, detects your plane, registers the memory tools for Claude Code (and therefore every Omnigent-managed session), turns on automatic capture and recall, and runs a health check. Then you just work — in `claude` or `omni claude` — and memory accumulates and surfaces on its own.

---

*Omnigent is a Databricks open-source project; Memora is from Microsoft Research. Neither is affiliated with this repository, which is an independent MIT-licensed integration.*
