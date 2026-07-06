import os

# In-process embeddings so a subscription-only user needs no embedding
# endpoint and no key. Default: Chroma's bundled ONNX MiniLM (384-dim,
# CPU, ships inside the chromadb dependency — no account, no daemon).
#
# This is installed as a runtime shim over Memora's OpenAI-only embedding
# function (a monkeypatch of our own process, not an edit to Memora's files),
# keeping the v1 "zero-patch" property. If MEMORA_EMBEDDING=api the user has
# opted into a served endpoint and Memora's stock path is left in place.
#
# We SUBCLASS chroma's own ONNX EF rather than wrapping it: chroma special-
# cases its native EF types for embedding shape and normalization on both the
# add and query paths, and a hand-rolled wrapper mis-shapes the query vector
# (chroma's rust binding then rejects it). Subclassing inherits the correct
# __call__ and only overrides the constructor to swallow Memora's (cfg) arg.

LocalEmbeddingFunction = None  # built lazily; chroma import is heavy


def _make_local_ef_cls():
    from chromadb.utils import embedding_functions

    class _LocalEmbeddingFunction(embedding_functions.ONNXMiniLM_L6_V2):
        def __init__(self, cfg=None):  # Memora constructs as (cfg)
            super().__init__()

    return _LocalEmbeddingFunction


def install_local_embedder():
    """Replace Memora's OpenAI embedding function with the in-process one,
    unless the user opted into a served embedding endpoint."""
    global LocalEmbeddingFunction
    if os.environ.get("MEMORA_EMBEDDING", "local") != "local":
        return "api"
    if LocalEmbeddingFunction is None:
        LocalEmbeddingFunction = _make_local_ef_cls()
    import memora.db_clients.chromadb_client as cc

    cc.ChromaDBEmbeddingFunction = LocalEmbeddingFunction
    return "local"
