from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage
from langgraph.prebuilt import ToolNode

from backend.agents.prompts import RAG_SYSTEM
from backend.agents.state import ConversationState
from backend.core.config import get_settings
from backend.tools.rag_tools import search_knowledge_base

settings = get_settings()

_tools = [search_knowledge_base]
_tool_node = ToolNode(_tools)

_llm = ChatAnthropic(
    model="claude-sonnet-4-6",
    api_key=settings.anthropic_api_key,
).bind_tools(_tools)


async def rag_agent_node(state: ConversationState) -> dict[str, Any]:
    channel = state.get("channel", "web")
    system = RAG_SYSTEM
    if channel == "voice":
        system += "\n\nIMPORTANT: Keep all responses under 40 words for voice readability."

    messages = [SystemMessage(content=system)] + list(state["messages"])
    response = await _llm.ainvoke(messages)
    return {"messages": [response]}


def rag_should_continue(state: ConversationState) -> str:
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "rag_tools"
    return "__end__"
