from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage
from langgraph.prebuilt import ToolNode

from backend.agents.prompts import CANCELLATION_SYSTEM
from backend.agents.state import ConversationState
from backend.core.config import get_settings
from backend.tools.booking_tools import cancel_booking_by_token

settings = get_settings()

_tools = [cancel_booking_by_token]
_tool_node = ToolNode(_tools)

_llm = ChatAnthropic(
    model="claude-sonnet-4-6",
    api_key=settings.anthropic_api_key,
).bind_tools(_tools)


async def cancellation_agent_node(state: ConversationState) -> dict[str, Any]:
    channel = state.get("channel", "web")
    system = CANCELLATION_SYSTEM
    if channel == "voice":
        system += "\n\nIMPORTANT: Keep all responses under 40 words for voice readability."

    messages = [SystemMessage(content=system)] + list(state["messages"])
    response = await _llm.ainvoke(messages)
    return {"messages": [response]}


def cancellation_should_continue(state: ConversationState) -> str:
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "cancellation_tools"
    return "__end__"
