import os
from types import SimpleNamespace

# Central configuration surface for the memory engine. Everything is an
# environment variable so it composes with how MCP servers and hooks are
# already launched (the values are passed through Claude's `-e` flags or a
# shell export). `memora-mcp config` prints the resolved values.
#
# Defaults are chosen to be ECONOMICAL: a cheap model at low reasoning for the
# background write path, and in-process embeddings that cost nothing. Memory
# work should never compete with your real work for premium model budget.

# Cheap, more-than-good-enough extraction models per plane. Extraction is an
# easy task (read a transcript, emit JSON facts) — it does not want a frontier
# model on max reasoning.
_CHEAP_MODEL = {
    "subscription-claude": "haiku",       # Claude Max: haiku is a fraction of the quota
    "subscription-codex": None,           # let codex use its own default unless set
    "api": "gpt-4.1-mini",                # cheap OpenAI-class default
}


def settings():
    """Resolve the live configuration from the environment."""
    plane = os.environ.get("MEMORA_PLANE", "auto")
    return SimpleNamespace(
        # --- model plane (the write path) ---
        plane=plane,
        model=os.environ.get("MEMORA_LLM_MODEL"),          # None => cheap per-plane default
        reasoning=os.environ.get("MEMORA_REASONING", "low"),  # low | medium | high
        distill_timeout=int(os.environ.get("MEMORA_DISTILL_TIMEOUT", "300")),
        # --- capture policy (what to store) ---
        # Default "rich": store more, trust Memora's retrieval to rank. Because
        # Memora decouples storage from retrieval (only abstractions + cues are
        # indexed, never the value), a fuller store does not degrade recall the
        # way a fuller RAG index would.
        capture=os.environ.get("MEMORA_CAPTURE", "rich"),  # lean | balanced | rich
        min_turns=int(os.environ.get("MEMORA_MIN_TURNS", "3")),
        max_distills_per_day=int(os.environ.get("MEMORA_MAX_DISTILLS_PER_DAY", "300")),
        session_summary=os.environ.get("MEMORA_SESSION_SUMMARY", "1") == "1",
        # --- embeddings (the read path) ---
        embedding=os.environ.get("MEMORA_EMBEDDING", "local"),  # local | api
        embedding_model=os.environ.get("MEMORA_EMBEDDING_MODEL", "text-embedding-3-small"),
        # --- recall ---
        recall_max_lines=int(os.environ.get("MEMORA_RECALL_LINES", "8")),
        recall_max_bytes=int(os.environ.get("MEMORA_RECALL_BYTES", "1500")),
    )


def model_for(kind: str) -> str | None:
    """The extraction model for a plane: explicit override, else the cheap
    per-plane default."""
    override = os.environ.get("MEMORA_LLM_MODEL")
    if override:
        return override
    return _CHEAP_MODEL.get(kind)


def as_table() -> list[tuple[str, str, str]]:
    """(env var, value, note) rows for `memora-mcp config`."""
    s = settings()
    return [
        ("MEMORA_PLANE", s.plane, "auto-detect, or force: subscription-claude|subscription-codex|api"),
        ("MEMORA_LLM_MODEL", s.model or "(cheap default)", "extraction model; default haiku (claude) / gpt-4.1-mini (api)"),
        ("MEMORA_REASONING", s.reasoning, "reasoning/effort for extraction: low|medium|high"),
        ("MEMORA_CAPTURE", s.capture, "how much to store: lean|balanced|rich (rich = store more, trust recall)"),
        ("MEMORA_SESSION_SUMMARY", "on" if s.session_summary else "off", "also store a short episodic summary per session"),
        ("MEMORA_MAX_DISTILLS_PER_DAY", str(s.max_distills_per_day), "write-cap safety valve"),
        ("MEMORA_MIN_TURNS", str(s.min_turns), "skip capturing sessions shorter than this"),
        ("MEMORA_EMBEDDING", s.embedding, "local (in-process, no key) | api (served endpoint)"),
        ("MEMORA_EMBEDDING_MODEL", s.embedding_model if s.embedding == "api" else "in-process MiniLM", "embedding model when MEMORA_EMBEDDING=api"),
        ("MEMORA_DISTILL_TIMEOUT", str(s.distill_timeout) + "s", "per-distill model-call timeout"),
    ]
