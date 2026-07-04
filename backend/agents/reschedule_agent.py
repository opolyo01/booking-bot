import json
import logging
from typing import Any, Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from backend.agents.booking_agent import _attempt_direct_booking, _extract_booking_details, _slot_is_available
from backend.agents.prompts import RESCHEDULE_SYSTEM
from backend.agents.state import ConversationState
from backend.core.config import get_settings
from backend.tools.availability_tools import get_available_slots
from backend.tools.booking_tools import cancel_booking_by_token, confirm_booking

settings = get_settings()

_tools = [cancel_booking_by_token, get_available_slots]
_tool_node = ToolNode(_tools)

_llm = ChatAnthropic(
    model="claude-sonnet-4-6",
    api_key=settings.anthropic_api_key,
).bind_tools(_tools)


async def reschedule_agent_node(state: ConversationState) -> dict[str, Any]:
    messages_list = list(state["messages"])

    # Once the new booking is confirmed, lock the session
    if state.get("booking_confirmed"):
        return {"messages": [AIMessage(content=(
            "Your rescheduled booking is already confirmed. "
            "To make another change, please start a new conversation."
        ))]}

    # After cancel + slot confirmation, try to auto-book
    details = await _extract_booking_details(messages_list)
    if details and details.has_all_info:
        try:
            available = await _slot_is_available(details.slot_start_utc, details.meeting_type)
        except Exception:
            available = False

        if available:
            result = await _attempt_direct_booking(details, state)
            if result:
                return result

    from datetime import datetime, timezone as _tz
    today_str = datetime.now(_tz.utc).strftime("%A, %B %d, %Y")
    channel = state.get("channel", "web")
    system = RESCHEDULE_SYSTEM + f"\n\nToday's date is {today_str} (UTC)."
    if channel == "voice":
        system += "\n\nIMPORTANT: Keep all responses under 60 words for voice readability."

    response = await _llm.ainvoke([SystemMessage(content=system)] + messages_list)
    return {"messages": [response]}


def reschedule_should_continue(state: ConversationState) -> str:
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "reschedule_tools"
    return "__end__"
