import sys


def _check(label, fn):
    try:
        detail = fn()
    except Exception as e:
        print(f"FAIL  {label}: {e}")
        return False
    print(f"ok    {label}" + (f" ({detail})" if detail else ""))
    return True


def run() -> int:
    """Verify the chain the way it actually runs: import, config, model plane,
    in-process embedder, store. No OpenAI key is required on the subscription
    plane — this checks what memory truly depends on."""
    from memora_mcp import planes
    from memora_mcp.config import build_cfg, ensure_memora_importable, memora_home, user_id

    results = []

    def imp():
        ensure_memora_importable()
        import memora
        import os
        return os.path.dirname(memora.__file__)

    results.append(_check("memora import + embedder shim", imp))
    if not results[-1]:
        print("\nhint: run install.sh, or set MEMORA_SRC=/path/to/Memora/src")
        return 1

    cfg = {}

    def conf():
        nonlocal cfg
        cfg = build_cfg()
        return f"embed={'in-process MiniLM' if _local_embed() else cfg.openai.embedding_model}"

    def _local_embed():
        import os
        return os.environ.get("MEMORA_EMBEDDING", "local") == "local"

    results.append(_check("config", conf))

    def plane():
        p = planes.detect()
        k = p["kind"]
        if k == "none":
            raise RuntimeError(
                "no model plane: log in to claude or codex (subscription), "
                "or set OPENAI_API_KEY / a gateway"
            )
        if k.startswith("subscription"):
            return f"{k} (rides your subscription — no API key needed)"
        return k

    results.append(_check("model plane", plane))

    def embed():
        from memora_mcp.embedder import install_local_embedder
        import os
        if os.environ.get("MEMORA_EMBEDDING", "local") != "local":
            return "served endpoint (opted in)"
        install_local_embedder()
        from memora_mcp.embedder import LocalEmbeddingFunction
        ef = LocalEmbeddingFunction()
        v = ef(["ping"])
        return f"in-process MiniLM, dim={len(v[0])}, no key"

    results.append(_check("embeddings", embed))

    def store():
        import chromadb
        c = chromadb.PersistentClient(path=cfg.memory.persist_path)
        return f"{cfg.memory.persist_path}, {len(c.list_collections())} collections, user={user_id()}"

    results.append(_check("store", store))

    def sidecar():
        from memora_mcp.sidecar import Sidecar
        s = Sidecar()
        st = s.stats()
        s.close()
        return f"{st['active']} active, {st['tombstoned']} tombstoned"

    results.append(_check("sidecar", sidecar))

    def hooks():
        import json
        import os
        p = os.path.expanduser("~/.claude/settings.json")
        if not os.path.exists(p):
            return "not registered (run: memora-mcp enable)"
        h = json.load(open(p)).get("hooks", {})
        ours = [e for e in h.get("SessionStart", []) for x in e.get("hooks", []) if "memora_mcp.hooks" in x.get("command", "")]
        return "automemory ON" if ours else "not registered (run: memora-mcp enable)"

    _check("automemory hooks", hooks)

    if all(results):
        print(f"\nall checks passed — home: {memora_home()}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(run())
