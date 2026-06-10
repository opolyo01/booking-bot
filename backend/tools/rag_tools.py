import json

from langchain_core.tools import tool

from backend.services.pinecone_service import similarity_search


@tool
async def search_knowledge_base(query: str) -> str:
    """
    Search Oleg Polyakov's knowledge base for relevant information.
    Use this to answer questions about his background, skills, experience,
    and the types of meetings available.

    Args:
        query: A natural language question or topic to search for.

    Returns:
        Relevant text passages from the knowledge base.
    """
    try:
        results = await similarity_search(query, top_k=4)
    except Exception as e:
        return f"Knowledge base search unavailable: {e}"

    if not results:
        return "No relevant information found."

    passages = [
        f"[Score: {r['score']:.2f}] {r['text']}"
        for r in results
        if r["score"] > 0.4
    ]
    return json.dumps(passages) if passages else "No sufficiently relevant information found."
