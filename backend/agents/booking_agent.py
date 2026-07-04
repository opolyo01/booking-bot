import json
import logging
from typing import Any, Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from backend.agents.prompts import BOOKING_SYSTEM
from backend.agents.state import ConversationState
from backend.core.config import get_settings
from backend.tools.availability_tools import get_available_slots
from backend.tools.booking_tools import confirm_booking

settings = get_settings()

_tools = [get_available_slots]  # confirm_booking is called directly, not via LLM tool use
_tool_node = ToolNode(_tools)

_llm = ChatAnthropic(
    model="claude-sonnet-4-6",
    api_key=settings.anthropic_api_key,
).bind_tools(_tools)


# ── Extraction schema ─────────────────────────────────────────────────────────

class _BookingDetails(BaseModel):
    has_all_info: bool = False
    name: Optional[str] = None
    email: Optional[str] = None
    meeting_type: Optional[str] = None   # job_offer | consulting | training | meetup_hackathon
    slot_start_utc: Optional[str] = None  # ISO 8601 UTC e.g. "2026-06-19T13:00:00+00:00"
    topic: Optional[str] = None


_extractor = ChatAnthropic(
    model="claude-haiku-4-5-20251001",
    api_key=settings.anthropic_api_key,
)


async def _extract_booking_details(messages: list) -> Optional[_BookingDetails]:
    lines = []
    for m in messages[-14:]:
        if isinstance(m, ToolMessage):
            continue
        content = getattr(m, "content", None)
        if isinstance(content, list):
            # Tool-call AIMessages have list content — extract text parts only
            text = " ".join(
                p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"
            )
        elif isinstance(content, str):
            text = content
        else:
            continue
        if not text.strip():
            continue
        role = "User" if isinstance(m, HumanMessage) else "Assistant"
        lines.append(f"{role}: {text[:800]}")

    if not lines:
        return None

    conversation = "\n".join(lines)
    prompt = f"""You extract structured booking data from a conversation.

Conversation:
{conversation}

Output ONLY a JSON object (no markdown, no explanation):
{{
  "has_all_info": true/false,
  "name": "full name or null",
  "email": "email or null",
  "meeting_type": "consulting|job_offer|training|meetup_hackathon or null",
  "slot_start_utc": "ISO 8601 UTC datetime e.g. 2026-06-19T13:00:00+00:00 or null",
  "topic": "topic or null"
}}

Set has_all_info=true ONLY when name, email, meeting_type AND slot_start_utc are all non-null.
For slot_start_utc always include both date AND time (not midnight unless user said midnight)."""

    try:
        response = await _extractor.ainvoke([HumanMessage(content=prompt)])
        raw = response.content.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        result = _BookingDetails(**data)
        logger.info("Extraction result: %s", result.model_dump())
        return result
    except Exception as e:
        logger.error("Extraction failed: %s", e, exc_info=True)
        return None


# ── Main node ─────────────────────────────────────────────────────────────────

async def _attempt_direct_booking(
    details: "_BookingDetails", state: ConversationState
) -> Optional[dict[str, Any]]:
    """Try to book directly. Returns state update dict on success, None on failure."""
    result_json = await confirm_booking.ainvoke({
        "name": details.name,
        "email": details.email,
        "meeting_type": details.meeting_type,
        "slot_start": details.slot_start_utc,
        "user_timezone": state.get("user_timezone") or "UTC",
        "topic": details.topic or "",
    })
    data = json.loads(result_json)
    if "booking_id" not in data:
        return None

    from datetime import datetime as _dt
    import zoneinfo as _zi
    tz_name = state.get("user_timezone") or "UTC"
    try:
        tz = _zi.ZoneInfo(tz_name)
        local_dt = _dt.fromisoformat(details.slot_start_utc).astimezone(tz)
        time_display = local_dt.strftime("%A, %B %-d at %-I:%M %p") + f" ({tz_name})"
    except Exception:
        time_display = details.slot_start_utc + " (UTC)"

    msg = AIMessage(content=(
        f"Your booking is confirmed! ✅\n\n"
        f"- **Name:** {details.name}\n"
        f"- **Meeting:** {details.meeting_type.replace('_', ' ').title()}\n"
        f"- **Time:** {time_display}\n"
        f"- **Topic:** {details.topic or '—'}\n\n"
        f"A confirmation email with a calendar invite is on its way to **{details.email}**. "
        f"You can cancel any time using the link in that email."
    ))
    return {
        "messages": [msg],
        "booking_id": data["booking_id"],
        "cancel_token": data.get("cancel_token"),
        "booking_confirmed": True,
    }


async def _slot_is_available(slot_start_utc: str, meeting_type: str) -> bool:
    """Verify a specific slot is actually open before booking."""
    from datetime import datetime, timezone as tz_module
    slot_dt = datetime.fromisoformat(slot_start_utc.replace("Z", "+00:00"))
    date_str = slot_dt.strftime("%Y-%m-%d")
    raw = await get_available_slots.ainvoke({"date": date_str, "meeting_type": meeting_type})
    slots_data = json.loads(raw)
    slots = slots_data if isinstance(slots_data, list) else slots_data.get("slots", [])
    return any(
        abs((datetime.fromisoformat(s["start"]) - slot_dt).total_seconds()) < 900
        for s in slots
    )


async def booking_agent_node(state: ConversationState) -> dict[str, Any]:
    messages_list = list(state["messages"])

    if state.get("booking_confirmed"):
        return {"messages": [AIMessage(content=(
            "You already have a confirmed booking in this session. "
            "To book another meeting, please start a new conversation."
        ))]}

    # Always try extraction — works on any turn once enough info is present
    details = await _extract_booking_details(messages_list)

    if details and details.has_all_info:
        # Always re-verify the specific requested slot right before booking.
        # A slot list shown earlier in the conversation — possibly for a
        # different date entirely — must never be trusted as proof that
        # *this* slot is still open.
        try:
            available = await _slot_is_available(details.slot_start_utc, details.meeting_type)
        except Exception:
            available = False

        if available:
            result = await _attempt_direct_booking(details, state)
            if result:
                return result

    # Regular LLM conversation turn (collects missing info or shows slots)
    from datetime import datetime, timezone as _tz
    today_str = datetime.now(_tz.utc).strftime("%A, %B %d, %Y")

    channel = state.get("channel", "web")
    system = BOOKING_SYSTEM + f"\n\nToday's date is {today_str} (UTC). Use this to resolve relative dates like 'next Monday', 'this Friday', 'tomorrow', etc. Always convert relative dates to YYYY-MM-DD before calling get_available_slots."
    if channel == "voice":
        system += "\n\nIMPORTANT: Keep all responses under 60 words for voice readability."

    response = await _llm.ainvoke([SystemMessage(content=system)] + messages_list)
    return {"messages": [response]}


def booking_should_continue(state: ConversationState) -> str:
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "booking_tools"
    return "__end__"
