import getpass
import os
import sys
from pathlib import Path


def memora_home() -> Path:
    return Path(os.environ.get("MEMORA_MCP_HOME", Path.home() / ".memora-mcp")).expanduser()


def ensure_memora_importable() -> None:
    """Make the Memora library importable.

    Memora ships no package metadata, so it can't be a pip dependency. Either
    install it onto the interpreter path yourself (e.g. a .pth file) or point
    MEMORA_SRC at the `src/` directory of a Memora checkout.
    """
    try:
        import memora  # noqa: F401
        return
    except ImportError:
        pass
    src = os.environ.get("MEMORA_SRC")
    if src and Path(src).is_dir():
        sys.path.insert(0, str(Path(src).expanduser().resolve()))
        try:
            import memora  # noqa: F401
            return
        except ImportError:
            pass
    raise RuntimeError(
        "memora is not importable. Clone https://github.com/microsoft/Memora, "
        "install its requirements.txt into this environment, and set "
        "MEMORA_SRC=/path/to/Memora/src"
    )


def build_cfg():
    """Build the OmegaConf config LocalMemoraClient expects.

    Mirrors Memora's quickstart schema, driven by environment variables. The
    OpenAI SDK also honors OPENAI_BASE_URL, which is how any OpenAI-compatible
    gateway (LiteLLM, Ollama, vLLM, Databricks) is reached without patching
    Memora.
    """
    from omegaconf import OmegaConf

    api_type = os.environ.get("OPENAI_API_TYPE", "openai")
    if api_type == "openai" and not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is required (Memora's OpenAI client refuses to "
            "start without one; for keyless local gateways set any value)"
        )

    store_path = memora_home() / "store"
    store_path.mkdir(parents=True, exist_ok=True)

    return OmegaConf.create(
        {
            "llm": {
                "model": os.environ.get("MEMORA_LLM_MODEL", "gpt-4.1-mini"),
                "seed": 42,
            },
            "openai": {
                "api_type": api_type,
                "llm_api_base": os.environ.get("AZURE_OPENAI_ENDPOINT", ""),
                "llm_api_version": os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
                "embedding_api_base": os.environ.get("AZURE_OPENAI_ENDPOINT", ""),
                "embedding_api_version": os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
                "embedding_deployment_name": os.environ.get(
                    "MEMORA_EMBEDDING_DEPLOYMENT",
                    os.environ.get("MEMORA_EMBEDDING_MODEL", "text-embedding-3-small"),
                ),
                "managed_identity": os.environ.get("AZURE_MANAGED_IDENTITY_CLIENT_ID"),
                "api_key": os.environ.get("OPENAI_API_KEY"),
                "embedding_model": os.environ.get("MEMORA_EMBEDDING_MODEL", "text-embedding-3-small"),
                "model": os.environ.get("MEMORA_LLM_MODEL", "gpt-4.1-mini"),
            },
            "memory": {
                "memory_store": "memora_mcp",
                "persist_path": str(store_path),
                "collection_name": os.environ.get("MEMORA_MCP_COLLECTION", "memora"),
                "distance": "cosine",
                "query_score_threshold": float(os.environ.get("MEMORA_QUERY_THRESHOLD", "0.4")),
                "update_score_threshold": float(os.environ.get("MEMORA_UPDATE_THRESHOLD", "0.8")),
                "force_rebuild": False,
                "enhance_query": False,
                "return_history": True,
                "multimodal_support": False,
                "top_k": 10,
                "cue_top_k": 10,
                "enable_hybrid_search": os.environ.get("MEMORA_HYBRID", "0") == "1",
                "enable_segmentation": False,
                "enable_episodic_memory": os.environ.get("MEMORA_EPISODIC", "0") == "1",
                "use_segments_as_episodic": False,
                "enable_cue_index": True,
            },
            "retrieval": {"strategy": "semantic"},
            "eval": {"max_workers": 5},
        }
    )


def user_id() -> str:
    return os.environ.get("MEMORA_MCP_USER", getpass.getuser())
