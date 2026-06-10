from typing import Optional

from fastembed import TextEmbedding
from pinecone import Pinecone, ServerlessSpec

from backend.core.config import get_settings

settings = get_settings()

_EMBED_DIM = 384  # BAAI/bge-small-en-v1.5 output dimension

_pc: Optional[Pinecone] = None
_embed_model: Optional[TextEmbedding] = None


def get_pinecone() -> Pinecone:
    global _pc
    if _pc is None:
        _pc = Pinecone(api_key=settings.pinecone_api_key)
    return _pc


def get_embed_model() -> TextEmbedding:
    global _embed_model
    if _embed_model is None:
        _embed_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    return _embed_model


def ensure_index() -> None:
    pc = get_pinecone()
    existing = {i.name: i for i in pc.list_indexes()}
    if settings.pinecone_index_name not in existing:
        pc.create_index(
            name=settings.pinecone_index_name,
            dimension=_EMBED_DIM,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
    elif existing[settings.pinecone_index_name].dimension != _EMBED_DIM:
        # Dimension mismatch from previous setup — recreate (safe: 0 vectors)
        pc.delete_index(settings.pinecone_index_name)
        pc.create_index(
            name=settings.pinecone_index_name,
            dimension=_EMBED_DIM,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )


async def upsert_documents(documents: list[dict]) -> None:
    """documents: list of {"id": str, "text": str, "metadata": dict}"""
    import asyncio
    pc = get_pinecone()
    index = pc.Index(settings.pinecone_index_name)
    model = get_embed_model()

    texts = [d["text"] for d in documents]
    # fastembed is sync — run in thread pool to avoid blocking event loop
    vectors = await asyncio.get_event_loop().run_in_executor(
        None, lambda: list(model.embed(texts))
    )

    to_upsert = [
        {
            "id": doc["id"],
            "values": vec.tolist(),
            "metadata": {**doc.get("metadata", {}), "text": doc["text"]},
        }
        for doc, vec in zip(documents, vectors)
    ]
    index.upsert(vectors=to_upsert)


async def similarity_search(query: str, top_k: int = 5) -> list[dict]:
    import asyncio
    pc = get_pinecone()
    index = pc.Index(settings.pinecone_index_name)
    model = get_embed_model()

    query_vec = await asyncio.get_event_loop().run_in_executor(
        None, lambda: next(model.query_embed(query))
    )
    result = index.query(vector=query_vec.tolist(), top_k=top_k, include_metadata=True)

    return [
        {"text": match.metadata.get("text", ""), "score": match.score}
        for match in result.matches
    ]
