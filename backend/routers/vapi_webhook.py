import hashlib
import hmac
import json
import re

from fastapi import APIRouter, HTTPException, Request
from langchain_core.messages import HumanMessage

from backend.core.config import get_settings

router = APIRouter(prefix="/webhook", tags=["vapi"])
settings = get_settings()


def _verify_signature(body: bytes, signature: str) -> bool:
    expected = hmac.new(
        settings.vapi_webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _strip_markdown(text: str) -> str:
    """Remove markdown so Vapi reads plain speech instead of symbols."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)   # bold
    text = re.sub(r"\*(.+?)\*", r"\1", text)         # italic
    text = re.sub(r"#+\s*", "", text)                 # headings
    text = re.sub(r"`(.+?)`", r"\1", text)            # inline code
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)  # links
    text = re.sub(r"^\s*[-*]\s+", "", text, flags=re.MULTILINE)  # bullets
    text = re.sub(r"\n{2,}", ". ", text)              # blank lines → pause
    return text.strip()


@router.post("/vapi/chat/completions")
async def vapi_custom_llm(request: Request):
    """
    Vapi Custom LLM endpoint (OpenAI-compatible).
    Vapi sends conversation messages; we run them through LangGraph
    and return a plain-speech response.
    """
    raw_body = await request.body()

    sig = request.headers.get("x-vapi-secret", "")
    if sig and not _verify_signature(raw_body, sig):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = json.loads(raw_body)

    call = payload.get("call", {})
    session_id = call.get("id", "vapi-unknown")

    messages = payload.get("messages", [])
    last_user = next(
        (m for m in reversed(messages) if m.get("role") == "user"), None
    )
    if not last_user:
        return {"choices": [{"message": {"role": "assistant", "content": "How can I help you?"}}]}

    graph = request.app.state.graph
    config = {"configurable": {"thread_id": session_id}}

    initial_state = {
        "messages": [HumanMessage(content=last_user["content"])],
        "session_id": session_id,
        "channel": "voice",
        "user_timezone": "UTC",
    }

    result = await graph.ainvoke(initial_state, config=config)

    last_ai = next(
        (
            m for m in reversed(result["messages"])
            if hasattr(m, "content")
            and not isinstance(m, HumanMessage)
            and not getattr(m, "tool_calls", None)
        ),
        None,
    )
    reply = _strip_markdown(last_ai.content if last_ai else "I'm sorry, I couldn't process that.")

    return {
        "choices": [{"message": {"role": "assistant", "content": reply}}]
    }
