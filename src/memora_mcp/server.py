import contextlib
import os
import sys
import threading

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from mcp.server.fastmcp import FastMCP

from memora_mcp.config import build_cfg, ensure_memora_importable, user_id

mcp = FastMCP("memora")

_client = None
_client_lock = threading.Lock()


def _get_client():
    global _client
    with _client_lock:
        if _client is None:
            ensure_memora_importable()
            from memora.memora_client import MemoraClient

            with contextlib.redirect_stdout(sys.stderr):
                _client = MemoraClient(cfg=build_cfg(), user_id=user_id())
        return _client


def _entry_lines(entries, with_scores: bool = False) -> list[str]:
    lines = []
    for e in entries:
        score = f" (score {e.score:.2f})" if with_scores and e.score is not None else ""
        kind = f" [{e.memory_type}]" if e.memory_type else ""
        lines.append(f"- {e.index}{kind}{score}: {e.value}")
    return lines


@mcp.tool()
def memory_save(content: str, kind: str = "note") -> str:
    """Persist a durable memory: a decision, preference, gotcha, config fact,
    or anything worth recalling in future sessions. The content is distilled
    into one or more indexed memories; near-duplicates are merged into the
    existing memory instead of being re-added.

    Args:
        content: The fact(s) to remember, in plain language.
        kind: "note" for facts/notes, "conversation" for a dialogue transcript.
    """
    # Route explicit saves through the same model plane as automatic capture
    # (subscription CLI / gateway) — NOT Memora's OpenAI-only add() — so no
    # OpenAI key is ever required.
    _get_client()  # ensures the embedder shim is installed
    import os

    from memora_mcp.distiller import project_key_for, store_from_text

    with contextlib.redirect_stdout(sys.stderr):
        stored = store_from_text(content, project_key=project_key_for(os.getcwd()),
                                 harness="explicit", explicit=True)
    if not stored:
        return "Nothing was stored."
    return f"Stored {len(stored)} memories:\n" + "\n".join(f"- {s}" for s in stored)


@mcp.tool()
def memory_search(query: str, top_k: int = 5) -> str:
    """Search memories by meaning, not keywords. Finds facts saved in any
    prior session by any agent, even when the phrasing differs. Use this
    before re-deriving project knowledge, preferences, or past decisions.

    Args:
        query: What you want to know, in plain language.
        top_k: Maximum number of memories to return.
    """
    client = _get_client()
    with contextlib.redirect_stdout(sys.stderr):
        entries = client.query(query, top_k=top_k, enable_hybrid_search=True)
        if not entries:
            # Memora's default BOTH mode drops all primary hits when the cue
            # leg returns nothing (core/memory.py fuses only when both legs
            # are non-empty), so an empty result must be retried against the
            # primary index alone before it can be trusted.
            from memora.core.memory import QueryMode

            entries = client.query(query, top_k=top_k, query_mode=QueryMode.PRIMARY_ONLY)
    if not entries:
        return "No matching memories."
    return "\n".join(_entry_lines(entries, with_scores=True))


@mcp.tool()
def memory_get(key: str) -> str:
    """Fetch one memory's full record by its exact index key (as shown by
    memory_search or memory_list)."""
    client = _get_client()
    with contextlib.redirect_stdout(sys.stderr):
        record = client.get(key)
    if not record:
        return f"No memory with key: {key}"
    return str(record)


@mcp.tool()
def memory_forget(key: str) -> str:
    """Delete one memory by its exact index key. Use when a memory is wrong
    or obsolete."""
    client = _get_client()
    with contextlib.redirect_stdout(sys.stderr):
        client.delete(key)
    return f"Deleted: {key}"


@mcp.tool()
def memory_list(limit: int = 20) -> str:
    """List stored memories (most useful for auditing what the store knows)."""
    client = _get_client()
    with contextlib.redirect_stdout(sys.stderr):
        entries = client.list_memories(limit=limit)
    if not entries:
        return "The memory store is empty."
    return f"{len(entries)} memories:\n" + "\n".join(_entry_lines(entries))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
