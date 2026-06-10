import json
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from backend.agents.booking_agent import (
    booking_agent_node,
    booking_should_continue,
)
from backend.agents.cancellation_agent import (
    cancellation_agent_node,
    cancellation_should_continue,
)
from backend.agents.prompts import ORCHESTRATOR_SYSTEM
from backend.agents.rag_agent import rag_agent_node, rag_should_continue
from backend.agents.state import ConversationState
from backend.core.config import get_settings
from backend.tools.availability_tools import get_available_slots
from backend.tools.booking_tools import cancel_booking_by_token, confirm_booking
from backend.tools.rag_tools import search_knowledge_base

settings = get_settings()

_router_llm = ChatAnthropic(
    model="claude-haiku-4-5-20251001",  # fast + cheap for routing only
    api_key=settings.anthropic_api_key,
)


async def orchestrator_node(state: ConversationState) -> dict[str, Any]:
    """Classifies user intent and updates state.intent."""
    last_human = next(
        (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        None,
    )
    if not last_human:
        return {"intent": "unknown"}

    messages = [
        SystemMessage(content=ORCHESTRATOR_SYSTEM),
        HumanMessage(content=last_human.content),
    ]
    response = await _router_llm.ainvoke(messages)

    content = response.content.strip()
    try:
        # Handle both {"intent": "book"} and raw "book"
        if content.startswith("{"):
            data = json.loads(content)
            intent = data.get("intent", "unknown")
        else:
            intent = content.lower().strip('"\'')
    except (json.JSONDecodeError, AttributeError):
        intent = "unknown"

    # Fallback: keyword scan if model didn't follow instructions
    if intent not in ("book", "faq", "cancel"):
        lower = last_human.content.lower()
        if any(w in lower for w in ("book", "schedule", "meeting", "appointment",
                                     "session", "slot", "reserve", "availability")):
            intent = "book"
        elif any(w in lower for w in ("cancel", "cancell")):
            intent = "cancel"
        else:
            intent = "faq"

    # Also catch "interested in a <type> session/meeting" phrasing that the LLM
    # may classify as FAQ — they are booking intents.
    if intent == "faq":
        lower = last_human.content.lower()
        booking_signals = ("interested in a", "want to book", "want to schedule",
                           "like to book", "like to schedule", "want a session",
                           "book a session", "schedule a session", "set up a",
                           "arrange a", "organize a meeting", "invite oleg",
                           "have oleg", "want oleg to")
        if any(sig in lower for sig in booking_signals):
            intent = "book"

    # Preserve booking intent mid-flow — follow-up messages (dates, names, slot
    # confirmations) won't contain booking keywords and get mis-routed to faq.
    # Only an explicit cancel breaks out of an active booking conversation.
    if state.get("intent") == "book" and intent != "cancel":
        intent = "book"

    return {"intent": intent}


def route_after_orchestrator(state: ConversationState) -> str:
    intent = state.get("intent", "unknown")
    if intent == "book":
        return "booking"
    if intent == "faq":
        return "rag"
    if intent == "cancel":
        return "cancellation"
    return "rag"  # default: treat unknown as FAQ


def build_graph(checkpointer=None):
    workflow = StateGraph(ConversationState)

    # Nodes
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("booking", booking_agent_node)
    workflow.add_node(
        "booking_tools",
        ToolNode([get_available_slots]),
    )
    workflow.add_node("rag", rag_agent_node)
    workflow.add_node("rag_tools", ToolNode([search_knowledge_base]))
    workflow.add_node("cancellation", cancellation_agent_node)
    workflow.add_node(
        "cancellation_tools",
        ToolNode([cancel_booking_by_token]),
    )

    # Edges
    workflow.add_edge(START, "orchestrator")
    workflow.add_conditional_edges(
        "orchestrator",
        route_after_orchestrator,
        {"booking": "booking", "rag": "rag", "cancellation": "cancellation"},
    )

    # Booking sub-loop
    workflow.add_conditional_edges(
        "booking",
        booking_should_continue,
        {"booking_tools": "booking_tools", "__end__": END},
    )
    workflow.add_edge("booking_tools", "booking")

    # RAG sub-loop
    workflow.add_conditional_edges(
        "rag",
        rag_should_continue,
        {"rag_tools": "rag_tools", "__end__": END},
    )
    workflow.add_edge("rag_tools", "rag")

    # Cancellation sub-loop
    workflow.add_conditional_edges(
        "cancellation",
        cancellation_should_continue,
        {"cancellation_tools": "cancellation_tools", "__end__": END},
    )
    workflow.add_edge("cancellation_tools", "cancellation")

    return workflow.compile(checkpointer=checkpointer)
