import hashlib
import hmac
import json
import logging
import re
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

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


def _extract_text(value) -> str:
    """Best-effort text extraction from LangChain messages/chunks/content blocks."""
    if value is None:
        return ""

    text_attr = getattr(value, "text", None)
    if callable(text_attr):
        try:
            text_attr = text_attr()
        except TypeError:
            text_attr = None
    if isinstance(text_attr, str) and text_attr.strip():
        return text_attr

    if isinstance(value, str):
        return value

    if isinstance(value, dict):
        if value.get("type") == "text" and isinstance(value.get("text"), str):
            return value["text"]
        content = value.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return _extract_text(content)
        return ""

    content = getattr(value, "content", value)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def _response_meta(payload: dict, session_id: str) -> tuple[str, int, str]:
    response_id = f"chatcmpl-{session_id}"
    created = int(time.time())
    model = payload.get("model") or "custom-vapi"
    return response_id, created, model


def _stream_chunk(
    *,
    response_id: str,
    created: int,
    model: str,
    content: str | None = None,
    finish_reason: str | None = None,
    include_role: bool = False,
) -> str:
    delta = {}
    if include_role:
        delta["role"] = "assistant"
    if content is not None:
        delta["content"] = content

    body = {
        "id": response_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "logprobs": None,
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(body)}\n\n"


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
    response_id, created, model = _response_meta(payload, session_id)

    messages = payload.get("messages", [])
    last_user = next(
        (m for m in reversed(messages) if m.get("role") == "user"), None
    )
    if not last_user:
        return {
            "id": response_id,
            "object": "chat.completion",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "How can I help you?"},
                    "logprobs": None,
                    "finish_reason": "stop",
                }
            ],
        }

    graph = request.app.state.graph
    config = {"configurable": {"thread_id": session_id}}

    initial_state = {
        "messages": [HumanMessage(content=_extract_text(last_user.get("content", "")))],
        "session_id": session_id,
        "channel": "voice",
        "user_timezone": "UTC",
    }

    stream = payload.get("stream", False)
    logger.info("Vapi request: session=%s stream=%s", session_id, stream)

    if stream:
        async def event_stream():
            streamed_any = False
            role_sent = False
            fallback_message = None

            try:
                async for event in graph.astream_events(initial_state, config=config, version="v2"):
                    kind = event["event"]
                    meta = event.get("metadata", {})

                    # Capture the final assistant text in case token streaming is empty.
                    if kind == "on_chain_end" and meta.get("langgraph_node") in _AGENT_NODES:
                        data = event.get("data")
                        output = data.get("output") if isinstance(data, dict) else None
                        msgs = list(output.get("messages", []) if isinstance(output, dict) else [])
                        for msg in reversed(msgs):
                            if isinstance(msg, HumanMessage) or getattr(msg, "tool_calls", None):
                                continue
                            text = _strip_markdown(_extract_text(msg))
                            if text:
                                fallback_message = text
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

                    content = _strip_markdown(_extract_text(chunk))
                    if content:
                        streamed_any = True
                        yield _stream_chunk(
                            response_id=response_id,
                            created=created,
                            model=model,
                            content=content,
                            include_role=not role_sent,
                        )
                        role_sent = True
            except Exception:
                logger.exception("Vapi streaming response failed for session %s", session_id)
                if not streamed_any:
                    fallback_message = fallback_message or (
                        "I'm sorry, something went wrong while processing your message."
                    )

            if not streamed_any and fallback_message:
                yield _stream_chunk(
                    response_id=response_id,
                    created=created,
                    model=model,
                    content=fallback_message,
                    include_role=True,
                )

            yield _stream_chunk(
                response_id=response_id,
                created=created,
                model=model,
                finish_reason="stop",
            )
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

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
    reply_text = _extract_text(last_ai) if last_ai else ""
    reply = _strip_markdown(reply_text or "I'm sorry, I couldn't process that.")

    return {
        "id": response_id,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": reply},
                "logprobs": None,
                "finish_reason": "stop",
            }
        ],
    }
