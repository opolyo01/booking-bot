import hashlib
import hmac
import json
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage

from backend.core.config import get_settings

router = APIRouter(prefix="/webhook", tags=["vapi"])
settings = get_settings()

_AGENT_NODES = {"booking", "rag", "cancellation"}


def _verify_signature(body: bytes, signature: str) -> bool:
    expected = hmac.new(
        settings.vapi_webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _strip_markdown(text: str) -> str:
    """Remove markdown so Vapi reads plain speech instead of symbols."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"#+\s*", "", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"^\s*[-*]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{2,}", ". ", text)
    return text.strip()


@router.post("/vapi/chat/completions")
async def vapi_custom_llm(request: Request):
    """
    Vapi Custom LLM endpoint (OpenAI-compatible).
    Supports both streaming (SSE) and non-streaming responses.
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

    if payload.get("stream", False):
        async def event_stream():
            streamed_any = False
            fallback_message = None

            async for event in graph.astream_events(initial_state, config=config, version="v2"):
                kind = event["event"]
                meta = event.get("metadata", {})

                # Capture final message for direct-booking path (no LLM tokens emitted)
                if kind == "on_chain_end" and meta.get("langgraph_node") in _AGENT_NODES:
                    data = event.get("data")
                    output = data.get("output") if isinstance(data, dict) else None
                    msgs = list(output.get("messages", []) if isinstance(output, dict) else [])
                    for msg in reversed(msgs):
                        if (
                            hasattr(msg, "content")
                            and not isinstance(msg, HumanMessage)
                            and not getattr(msg, "tool_calls", None)
                            and isinstance(msg.content, str)
                            and msg.content
                        ):
                            fallback_message = _strip_markdown(msg.content)
                            break

                if kind != "on_chat_model_stream":
                    continue
                if meta.get("langgraph_node") not in _AGENT_NODES:
                    continue
                # Skip Haiku (orchestrator + extractor) — only stream Sonnet agent responses
                if "haiku" in meta.get("ls_model_name", "").lower():
                    continue

                chunk = event["data"]["chunk"]
                if getattr(chunk, "tool_call_chunks", None):
                    continue

                content = chunk.content if isinstance(chunk.content, str) else ""
                if content:
                    streamed_any = True
                    yield (
                        f"data: {json.dumps({'choices': [{'delta': {'role': 'assistant', 'content': content}, 'finish_reason': None}]})}\n\n"
                    )

            # Fallback: direct booking confirmation has no LLM tokens
            if not streamed_any and fallback_message:
                yield (
                    f"data: {json.dumps({'choices': [{'delta': {'role': 'assistant', 'content': fallback_message}, 'finish_reason': None}]})}\n\n"
                )

            yield f"data: {json.dumps({'choices': [{'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    # Non-streaming fallback
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

    return {"choices": [{"message": {"role": "assistant", "content": reply}}]}
