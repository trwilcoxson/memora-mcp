import os
import sys


def _check(label: str, fn):
    try:
        detail = fn()
    except Exception as e:
        print(f"FAIL  {label}: {e}")
        return False
    print(f"ok    {label}" + (f" ({detail})" if detail else ""))
    return True


def run() -> int:
    """Verify the whole chain: import, config, chat model, embeddings, store."""
    from memora_mcp.config import build_cfg, ensure_memora_importable, memora_home, user_id

    results = []

    def imp():
        ensure_memora_importable()
        import memora
        return os.path.dirname(memora.__file__)

    results.append(_check("memora import", imp))
    if not results[-1]:
        print("\nhint: run install.sh, or set MEMORA_SRC=/path/to/Memora/src")
        return 1

    cfg = {}

    def conf():
        nonlocal cfg
        cfg = build_cfg()
        return f"llm={cfg.llm.model}, embed={cfg.openai.embedding_model}"

    results.append(_check("config", conf))
    if not results[-1]:
        print("\nhint: set OPENAI_API_KEY (any value for keyless local gateways)")
        return 1

    from openai import OpenAI

    client = OpenAI(api_key=cfg.openai.api_key or "unused")

    def chat():
        r = client.chat.completions.create(
            model=cfg.llm.model, messages=[{"role": "user", "content": "ping"}], max_tokens=1
        )
        return r.model

    results.append(_check("chat model", chat))

    def embed():
        r = client.embeddings.create(input=["ping"], model=cfg.openai.embedding_model)
        return f"dim={len(r.data[0].embedding)}"

    results.append(_check("embedding model", embed))

    def store():
        import chromadb
        c = chromadb.PersistentClient(path=cfg.memory.persist_path)
        cols = c.list_collections()
        return f"{cfg.memory.persist_path}, {len(cols)} collections, user={user_id()}"

    results.append(_check("store", store))

    if all(results):
        print(f"\nall checks passed — home: {memora_home()}")
        return 0
    print(
        "\nhint: chat/embedding failures usually mean OPENAI_BASE_URL is wrong, the "
        "endpoint is down, or the model name is not served there (Memora requires a "
        "GPT-looking chat model name; alias local models, e.g. "
        "`ollama cp llama3.2:3b gpt-4-local`)"
    )
    return 1


if __name__ == "__main__":
    sys.exit(run())
