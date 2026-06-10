# LangChain & LangGraph in the Booking Bot — Full Tutorial

> A deep-dive into every LangChain/LangGraph pattern used in this project.  
> By the end you will understand *why* each design decision was made, not just *what* the code does.

---

## Table of Contents

1. [Big Picture — What Is LangGraph?](#1-big-picture--what-is-langgraph)
2. [The Graph Architecture](#2-the-graph-architecture)
3. [State — The Graph's Memory](#3-state--the-graphs-memory)
4. [The Orchestrator Node — Intent Router](#4-the-orchestrator-node--intent-router)
5. [LangChain Tools — The @tool Decorator](#5-langchain-tools--the-tool-decorator)
6. [ToolNode — Automatic Tool Execution](#6-toolnode--automatic-tool-execution)
7. [The Booking Agent — Multi-Step Collection](#7-the-booking-agent--multi-step-collection)
8. [The RAG Agent — Knowledge Base Search](#8-the-rag-agent--knowledge-base-search)
9. [The Cancellation Agent](#9-the-cancellation-agent)
10. [Persistence — PostgreSQL Checkpointer](#10-persistence--postgresql-checkpointer)
11. [FastAPI Integration](#11-fastapi-integration)
12. [Voice vs Web — Channel-Aware Agents](#12-voice-vs-web--channel-aware-agents)
13. [Key Design Patterns Summary](#13-key-design-patterns-summary)

---

## 1. Big Picture — What Is LangGraph?

**LangChain** is a framework for building LLM-powered applications. It gives you:
- Standardized message types (`HumanMessage`, `AIMessage`, `SystemMessage`, `ToolMessage`)
- A uniform interface to call any LLM (`.invoke()`, `.ainvoke()`)
- The `@tool` decorator to define functions the LLM can call
- `bind_tools()` to attach tools to an LLM call

**LangGraph** builds *on top of* LangChain. It lets you define **stateful, multi-step agent workflows** as a directed graph. Instead of a single LLM call, you build a flow where:

- **Nodes** are async Python functions that read/write shared state
- **Edges** define which node runs next (fixed or conditional)
- **State** persists across every node execution inside one conversation turn
- A **checkpointer** stores state between turns, so the graph "remembers" prior messages

This project uses LangGraph because a booking assistant needs *multi-turn memory* and *branching logic*: different users have different intents (book / ask questions / cancel), and booking itself requires several back-and-forth steps.

---

## 2. The Graph Architecture

### The Full Graph

```
┌─────────────────────────────────────────────────────────────────────┐
│                          LangGraph StateGraph                       │
│                                                                     │
│   START                                                             │
│     │                                                               │
│     ▼                                                               │
│  ┌──────────────┐                                                   │
│  │  orchestrator │  ← classifies intent: book / faq / cancel        │
│  └──────────────┘                                                   │
│       │                                                             │
│       ├─── intent=book ────────────────────────────┐               │
│       │                                             ▼               │
│       │                                    ┌──────────────┐         │
│       │                                    │   booking    │         │
│       │                                    └──────────────┘         │
│       │                                         │                   │
│       │                               tool_calls?                   │
│       │                              /          \                   │
│       │                           yes            no                 │
│       │                            │              │                 │
│       │                    ┌───────────────┐     END               │
│       │                    │ booking_tools │                        │
│       │                    └───────────────┘                        │
│       │                            │                                │
│       │                            └──── back to booking ──────────┘│
│       │                                                             │
│       ├─── intent=faq ─────────────────────────────┐               │
│       │                                             ▼               │
│       │                                    ┌──────────────┐         │
│       │                                    │     rag      │         │
│       │                                    └──────────────┘         │
│       │                                         │                   │
│       │                               tool_calls?                   │
│       │                              /          \                   │
│       │                           yes            no                 │
│       │                            │              │                 │
│       │                    ┌────────────┐        END                │
│       │                    │ rag_tools  │                           │
│       │                    └────────────┘                           │
│       │                            │                                │
│       │                            └──── back to rag ───────────────┤
│       │                                                             │
│       └─── intent=cancel ──────────────────────────┐               │
│                                                     ▼               │
│                                            ┌──────────────────┐    │
│                                            │  cancellation    │    │
│                                            └──────────────────┘    │
│                                                 │                  │
│                                       tool_calls?                  │
│                                      /          \                  │
│                                   yes            no                │
│                                    │              │                │
│                          ┌────────────────────┐  END              │
│                          │ cancellation_tools │                   │
│                          └────────────────────┘                   │
│                                    │                               │
│                                    └──── back to cancellation ─────┘
└─────────────────────────────────────────────────────────────────────┘
```

### How the Graph is Built

The graph is assembled in `backend/agents/orchestrator.py`:

```python
# backend/agents/orchestrator.py

def build_graph(checkpointer=None):
    workflow = StateGraph(ConversationState)

    # 1. Register nodes (each is an async Python function)
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("booking", booking_agent_node)
    workflow.add_node("booking_tools", ToolNode([get_available_slots]))
    workflow.add_node("rag", rag_agent_node)
    workflow.add_node("rag_tools", ToolNode([search_knowledge_base]))
    workflow.add_node("cancellation", cancellation_agent_node)
    workflow.add_node("cancellation_tools", ToolNode([cancel_booking_by_token]))

    # 2. Every run starts at orchestrator
    workflow.add_edge(START, "orchestrator")

    # 3. Conditional routing after orchestrator
    workflow.add_conditional_edges(
        "orchestrator",
        route_after_orchestrator,           # function that returns a string key
        {"booking": "booking", "rag": "rag", "cancellation": "cancellation"},
    )

    # 4. Sub-loops for each agent (LLM → tool → LLM → ...)
    workflow.add_conditional_edges("booking", booking_should_continue,
        {"booking_tools": "booking_tools", "__end__": END})
    workflow.add_edge("booking_tools", "booking")   # tool result goes back to LLM

    workflow.add_conditional_edges("rag", rag_should_continue,
        {"rag_tools": "rag_tools", "__end__": END})
    workflow.add_edge("rag_tools", "rag")

    workflow.add_conditional_edges("cancellation", cancellation_should_continue,
        {"cancellation_tools": "cancellation_tools", "__end__": END})
    workflow.add_edge("cancellation_tools", "cancellation")

    return workflow.compile(checkpointer=checkpointer)
```

**Key concepts shown here:**
- `StateGraph(ConversationState)` — typed graph; every node receives/returns `ConversationState`
- `add_node(name, fn)` — registers any async Python function as a graph node
- `add_edge(a, b)` — unconditional: always go from `a` to `b`
- `add_conditional_edges(source, fn, mapping)` — `fn` inspects state and returns a key; `mapping` turns that key into the next node name
- `compile(checkpointer=...)` — returns the runnable graph; checkpointer wires in persistence

---

## 3. State — The Graph's Memory

### The TypedDict

```python
# backend/agents/state.py

from typing import Annotated, Literal, Optional
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

class ConversationState(TypedDict):
    # ── Core LangGraph field ──────────────────────────────
    messages: Annotated[list, add_messages]   # ← special reducer!
    session_id: str
    channel: Literal["web", "voice"]

    # ── Routing ───────────────────────────────────────────
    intent: Optional[Literal["book", "faq", "cancel", "unknown"]]

    # ── Collected booking details ─────────────────────────
    user_name: Optional[str]
    user_email: Optional[str]
    user_timezone: Optional[str]
    meeting_type: Optional[str]
    topic: Optional[str]
    available_slots: Optional[list[str]]
    selected_slot: Optional[str]

    # ── Result fields (set after booking) ─────────────────
    booking_id: Optional[str]
    cancel_token: Optional[str]
    booking_confirmed: bool
    cancel_token_input: Optional[str]
    error_message: Optional[str]
```

### The `add_messages` Reducer

This is the most important LangGraph concept in the state. Without it, every node returning `{"messages": [...]}` would *replace* the messages list. With it, messages are **appended**.

```
Turn 1:  state.messages = [HumanMessage("I want to book")]
         orchestrator runs → no change to messages
         booking_agent runs → appends AIMessage("What type of meeting?")
         state.messages = [Human, AI]

Turn 2:  You send HumanMessage("Consulting")
         LangGraph appends it → state.messages = [Human, AI, Human]
         booking_agent runs → appends AIMessage("What date works for you?")
         state.messages = [Human, AI, Human, AI]
```

The `Annotated[list, add_messages]` syntax is LangGraph's "reducer" pattern: `add_messages` is a function that knows how to merge two message lists (it also handles updating existing messages by ID).

### How Nodes Read and Write State

Every node is just a function:

```python
async def some_node(state: ConversationState) -> dict[str, Any]:
    # READ — access any key directly
    messages = state["messages"]
    intent = state.get("intent")

    # WRITE — return a dict with only the keys that changed
    # LangGraph merges this dict into the state
    return {"intent": "book"}   # only "intent" changes; everything else is preserved
```

Returning a partial dict is intentional — you don't need to return the full state, only what changed.

---

## 4. The Orchestrator Node — Intent Router

### What It Does

The orchestrator runs on *every* user message. It classifies intent so the graph knows which sub-agent to route to.

```
User message → orchestrator → sets state.intent → route_after_orchestrator → correct agent
```

### The Routing Function

```python
# backend/agents/orchestrator.py

async def orchestrator_node(state: ConversationState) -> dict[str, Any]:
    last_human = next(
        (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        None,
    )

    # ── Fast path: mid-booking flow ─────────────────────────────────────────────
    # Once we know the user is booking, preserve that intent for all follow-ups.
    # Follow-up messages like "June 23" or "John Smith" have no booking keywords
    # and would be misclassified as FAQ.  Only "cancel" breaks out.
    if state.get("intent") == "book":
        if any(w in last_human.content.lower() for w in ("cancel", "cancell")):
            return {"intent": "cancel"}
        return {"intent": "book"}   # ← skip LLM call entirely

    # ── LLM classification (first message only) ─────────────────────────────────
    messages = [
        SystemMessage(content=ORCHESTRATOR_SYSTEM),
        HumanMessage(content=last_human.content),
    ]
    response = await _router_llm.ainvoke(messages)
    # ... parse JSON, fallback keyword scan, return {"intent": value}
```

### Why Haiku for Routing?

```python
_router_llm = ChatAnthropic(
    model="claude-haiku-4-5-20251001",   # fast + cheap
    api_key=settings.anthropic_api_key,
)
```

Intent classification is a simple binary task. Haiku is ~10× cheaper and ~5× faster than Sonnet. The routing prompt is also short (one message), so accuracy is high. Sonnet is reserved for the actual agents that need deeper reasoning.

### The Routing Decision Function

```python
def route_after_orchestrator(state: ConversationState) -> str:
    intent = state.get("intent", "unknown")
    if intent == "book":    return "booking"
    if intent == "faq":     return "rag"
    if intent == "cancel":  return "cancellation"
    return "rag"    # default: treat unknown as FAQ
```

This function returns a *string key* that LangGraph maps to a node name via the `mapping` dict in `add_conditional_edges`.

---

## 5. LangChain Tools — The `@tool` Decorator

### What a Tool Is

A **tool** is a Python function the LLM can decide to call. The LLM doesn't execute code — it outputs a structured "tool call" (name + arguments as JSON), and LangGraph's `ToolNode` executes the real Python function.

### The `@tool` Decorator Pattern

```python
# backend/tools/availability_tools.py

from langchain_core.tools import tool

@tool
async def get_available_slots(date: str, meeting_type: str, preferred_time: str = "") -> str:
    """
    Return available booking slots for a given date and meeting type.

    Args:
        date: The date to check — any natural format works ("June 23", "2026-06-23", "06/23/2026").
        meeting_type: One of job_offer, consulting, training, meetup_hackathon.
        preferred_time: Optional time hint from the user (e.g. "11am", "14:30"). When provided,
                        the response includes a suggested_slot field with the nearest available slot.

    Returns:
        JSON with available slots (ISO 8601 UTC) and, if preferred_time was given, a suggested_slot.
    """
    # ... real implementation ...
    return json.dumps({"slots": [...], "suggested_slot": {...}})
```

The `@tool` decorator does several things:
1. Wraps the function as a `BaseTool` object with a `.name` and `.description`
2. Generates a JSON schema for the arguments from type annotations
3. The docstring becomes the tool description the LLM reads to decide whether to call it
4. Exposes `.ainvoke({"arg": value})` for direct programmatic calls

### How the LLM Decides to Call a Tool

When you call `_llm.ainvoke(messages)`, the LLM outputs an `AIMessage`. If it decides a tool is needed, the message includes `tool_calls`:

```python
# What the LLM returns when it wants to call get_available_slots:
AIMessage(
    content="",
    tool_calls=[{
        "id": "toolu_01...",
        "name": "get_available_slots",
        "args": {
            "date": "June 23",
            "meeting_type": "consulting",
            "preferred_time": "11am"
        }
    }]
)
```

The LLM never "runs" the tool — it just says "I want to call this with these args." LangGraph's `ToolNode` intercepts that and runs the real Python function.

### Direct Tool Invocation

Tools can also be called directly (bypassing LLM tool-call flow):

```python
# In booking_agent.py — direct call, no LLM involved
result_json = await confirm_booking.ainvoke({
    "name": details.name,
    "email": details.email,
    "meeting_type": details.meeting_type,
    "slot_start": details.slot_start_utc,
    "user_timezone": state.get("user_timezone") or "UTC",
    "topic": details.topic or "",
})
```

This is used for `confirm_booking` because we *never* want the LLM to decide when to create a booking — the agent logic makes that decision based on hard constraints.

---

## 6. ToolNode — Automatic Tool Execution

### What ToolNode Does

`ToolNode` is a pre-built LangGraph node that handles the tool execution loop:

```python
from langgraph.prebuilt import ToolNode

# In orchestrator.py:
workflow.add_node("booking_tools", ToolNode([get_available_slots]))
```

```
booking node (LLM) → returns AIMessage with tool_calls
    │
    ▼
booking_should_continue checks: does last message have tool_calls?
    │  yes
    ▼
booking_tools (ToolNode) → executes get_available_slots with the LLM's args
    │                     → appends ToolMessage(content=result, tool_call_id=...)
    ▼
back to booking (LLM) → now sees ToolMessage in history → continues reasoning
```

### The Continue/End Decision

Every agent has a `_should_continue` function:

```python
# booking_agent.py
def booking_should_continue(state: ConversationState) -> str:
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "booking_tools"   # → route to ToolNode
    return "__end__"             # → end this turn
```

This is the core of the **ReAct loop** (Reason + Act): the LLM reasons, optionally acts (calls a tool), gets the result appended as a `ToolMessage`, reasons again, and so on until it stops calling tools.

### Message Types in the Loop

```
┌─────────────────────────────────────────────────────────────────────┐
│  Conversation history after one booking turn with tool use:          │
│                                                                     │
│  1. HumanMessage    "I want to book a consulting call on June 23"   │
│  2. AIMessage       (tool_calls=[get_available_slots(...)]) ← LLM  │
│  3. ToolMessage     '{"slots":[...], "suggested_slot":{...}}'  ← ToolNode │
│  4. AIMessage       "The closest slot is 11:00 AM — does that work?"│
└─────────────────────────────────────────────────────────────────────┘
```

The entire history (messages 1–4) is persisted in PostgreSQL and sent back on the next turn so the LLM has full context.

---

## 7. The Booking Agent — Multi-Step Collection

### Overview

The booking agent is the most complex node. It has two modes:

```
┌──────────────────────────────────────────────────────────────────────┐
│                      booking_agent_node                              │
│                                                                      │
│  1. Extract booking details from conversation history (Haiku LLM)   │
│                                                                      │
│  2a. All info present AND slots were shown?                          │
│      → Direct booking path (confirm_booking.ainvoke)                │
│      → Return confirmed message + booking_confirmed: True           │
│                                                                      │
│  2b. All info present, no slots shown yet?                           │
│      → Verify slot is actually free (get_available_slots check)     │
│      → If free: direct booking path                                  │
│                                                                      │
│  3. Missing info OR slots not yet shown?                             │
│      → Regular LLM turn (Sonnet)                                    │
│      → LLM may call get_available_slots, or ask a follow-up Q       │
└──────────────────────────────────────────────────────────────────────┘
```

### The Extraction Pattern

Instead of relying on the conversational LLM to maintain structured state, a dedicated **extractor LLM** reads the conversation and fills a Pydantic model:

```python
class _BookingDetails(BaseModel):
    has_all_info: bool = False
    name: Optional[str] = None
    email: Optional[str] = None
    meeting_type: Optional[str] = None
    slot_start_utc: Optional[str] = None   # ISO 8601 UTC
    topic: Optional[str] = None

_extractor = ChatAnthropic(
    model="claude-haiku-4-5-20251001",    # cheap, just parsing
    api_key=settings.anthropic_api_key,
)
```

The extractor is called every turn with the last 14 messages. It outputs structured JSON which is parsed into `_BookingDetails`. This pattern is called **structured extraction** or **entity extraction**.

Why a separate extractor instead of tracking state manually?
- The conversational LLM may mention a slot in many forms ("11am", "the 11 o'clock one", "that first slot") — an LLM extractor handles all of these
- It's stateless — reads the full conversation each time, so it's robust to corrections ("actually, make that 2pm")
- Keeps the booking_agent_node code clean

### The `_slots_were_shown` Gate

```python
def _slots_were_shown(messages: list) -> bool:
    return any(
        isinstance(m, ToolMessage) and '"start"' in (m.content or "")
        for m in messages
    )
```

This prevents booking a time the user just typed ("book me at 3pm tomorrow") without the system first verifying that slot exists. The gate ensures `get_available_slots` was called at least once — meaning the LLM showed real slots to the user and the user chose one.

If slots weren't shown (one-shot intent), the booking path still works but goes through `_slot_is_available()` to verify before booking.

### Booking-Confirmed Guard

```python
async def booking_agent_node(state: ConversationState) -> dict[str, Any]:
    if state.get("booking_confirmed"):
        return {"messages": [AIMessage(content=(
            "You already have a confirmed booking in this session. "
            "To book another meeting, please start a new conversation."
        ))]}
    # ... rest of logic
```

Once `booking_confirmed: True` is in state (and checkpointed), any future message in the same session hits this guard immediately. The `session_id` maps to a PostgreSQL checkpoint thread, so the state is permanent until a new session is started.

### The System Prompt Strategy

```python
BOOKING_SYSTEM = """You are a booking assistant for Oleg Polyakov. You have ONE tool:
- get_available_slots(date, meeting_type, preferred_time="") — ...

Once you collect all required details, the system automatically creates the booking
— you do NOT call a booking tool yourself.

STRICT RULES — never break these:
- ALWAYS call get_available_slots before confirming any time — never invent a slot
- NEVER tell the user you "can't book" or that there's a technical issue
...
"""
```

Telling the LLM "the system automatically creates the booking — you do NOT call a booking tool yourself" is critical. It removes `confirm_booking` from the LLM's awareness entirely, preventing it from ever saying "I can't book" (because there's no booking tool for it to fail to call).

---

## 8. The RAG Agent — Knowledge Base Search

### Architecture

```
User asks: "What kind of meetings does Oleg offer?"
    │
    ▼
rag_agent_node (Sonnet LLM, bound to search_knowledge_base tool)
    │
    LLM decides to call search_knowledge_base("types of meetings Oleg offers")
    │
    ▼
rag_tools (ToolNode) → search_knowledge_base executes:
    │  1. Embed query with fastembed (BAAI/bge-small model)
    │  2. Query Pinecone vector index
    │  3. Return top-k matching text chunks
    │
    ▼
rag_agent_node again (LLM reads ToolMessage with retrieved chunks)
    │
    ▼
AIMessage("Oleg offers four types of meetings: consulting, job offers, ...")
```

### The Tool

```python
# backend/tools/rag_tools.py
@tool
async def search_knowledge_base(query: str) -> str:
    """Search Oleg's knowledge base for relevant information."""
    # Uses fastembed + Pinecone via pinecone_service.py
```

### The RAG Agent Node

```python
async def rag_agent_node(state: ConversationState) -> dict[str, Any]:
    channel = state.get("channel", "web")
    system = RAG_SYSTEM
    if channel == "voice":
        system += "\n\nIMPORTANT: Keep all responses under 40 words for voice readability."

    messages = [SystemMessage(content=system)] + list(state["messages"])
    response = await _llm.ainvoke(messages)
    return {"messages": [response]}
```

This is the simplest of the three agents — single Sonnet LLM call with tool access. The LLM decides when to call `search_knowledge_base` based on the question.

---

## 9. The Cancellation Agent

The cancellation agent follows the same pattern as the RAG agent but uses `cancel_booking_by_token`:

```
User: "I want to cancel" / "cancel token: abc123"
    │
    ▼
cancellation_agent_node (Sonnet)
    │
    If user provides token → LLM calls cancel_booking_by_token(token)
    If not → LLM asks for cancel token or directs to email link
    │
    ▼
cancellation_tools (ToolNode) → cancel_booking_by_token executes:
    │  1. Verify JWT cancel token
    │  2. Delete Google Calendar event
    │  3. Mark booking cancelled in DB
    │  4. Send cancellation email
    │
    ▼
AIMessage("Your booking has been cancelled.")
```

---

## 10. Persistence — PostgreSQL Checkpointer

### Why Persistence Matters

Without persistence, every API call is a fresh conversation — the bot has no memory of previous messages. With LangGraph's checkpointer, state is stored after every turn keyed by `thread_id`. The next turn loads that state automatically.

```
Turn 1:  thread_id="session-abc"  → state checkpointed to Postgres
Turn 2:  thread_id="session-abc"  → state loaded from Postgres → appended to → checkpointed
Turn N:  thread_id="session-abc"  → full history + booking_confirmed + intent all present
```

### Setting Up the Checkpointer

```python
# backend/main.py

from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    async with AsyncConnectionPool(
        conninfo=_pg_conninfo(),
        max_size=10,
        kwargs={"autocommit": True},
    ) as pool:
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()   # creates checkpoint tables if they don't exist
        app.state.graph = build_graph(checkpointer=checkpointer)

        yield   # app runs here

    await close_redis()
```

`AsyncPostgresSaver` creates two tables in Postgres: `checkpoints` and `checkpoint_writes`. LangGraph manages them automatically — you never write SQL for conversation history.

### Thread ID = Session ID

```python
# backend/routers/booking.py

config = {"configurable": {"thread_id": body.session_id}}
result = await graph.ainvoke(initial_state, config=config)
```

The `thread_id` is the key that LangGraph uses to look up and save checkpoints. In this project, `thread_id = session_id` — the frontend generates a UUID per browser tab and sends it with every message.

### What Gets Checkpointed

The entire `ConversationState` is checkpointed:
- All messages (Human, AI, Tool)
- `intent` — so mid-booking flow routing is preserved across turns
- `booking_confirmed` — so re-booking in same session is blocked
- `user_timezone`, `booking_id`, `cancel_token` — all booking metadata

---

## 11. FastAPI Integration

### The Full Request Lifecycle

```
POST /chat/message
  body: { session_id, message, channel, timezone }
    │
    ▼
chat_message() router function
    │
    ├─ 1. Gets graph from request.app.state.graph (built at startup)
    ├─ 2. Wraps user message in HumanMessage
    ├─ 3. Sets thread_id = session_id in config
    ├─ 4. Calls graph.ainvoke(initial_state, config=config)
    │       │
    │       └─ LangGraph runs:  orchestrator → agent → (tools → agent)* → END
    │
    ├─ 5. Extracts last AIMessage from result["messages"]
    └─ 6. Returns ChatMessageOut(reply, booking_confirmed, session_id)
```

```python
# backend/routers/booking.py

@router.post("/chat/message", response_model=ChatMessageOut)
async def chat_message(body: ChatMessageIn, request: Request):
    graph = request.app.state.graph

    config = {"configurable": {"thread_id": body.session_id}}
    initial_state = {
        "messages": [HumanMessage(content=body.message)],
        "session_id": body.session_id,
        "channel": body.channel,
        "user_timezone": body.timezone or "UTC",
    }

    result = await graph.ainvoke(initial_state, config=config)

    last_ai_msg = next(
        (m for m in reversed(result["messages"])
         if hasattr(m, "content")
         and not isinstance(m, HumanMessage)
         and not getattr(m, "tool_calls", None)),
        None,
    )
    reply = last_ai_msg.content if last_ai_msg else "I'm sorry, I couldn't process that."

    return ChatMessageOut(
        session_id=body.session_id,
        message=reply,
        booking_confirmed=result.get("booking_confirmed", False),
    )
```

### Why Only Pass Changed Fields to `ainvoke`

Notice we only pass `messages`, `session_id`, `channel`, and `user_timezone` in `initial_state` — not `intent`, `booking_confirmed`, etc. That's because:

1. LangGraph loads the full prior state from the checkpointer first
2. Then it *merges* `initial_state` on top of it
3. So only pass fields that change each turn; let the checkpointer preserve the rest

If you passed `intent: None` every turn, it would overwrite the preserved intent from the previous turn and break mid-flow routing.

---

## 12. Voice vs Web — Channel-Aware Agents

The project supports both a web chat interface and a voice interface via [Vapi](https://vapi.ai). The same LangGraph graph handles both:

```python
# In every agent node:
channel = state.get("channel", "web")
system = BASE_SYSTEM_PROMPT
if channel == "voice":
    system += "\n\nIMPORTANT: Keep all responses under 40 words for voice readability."
```

The `channel` field in state is set per-request by the router. For voice, the Vapi webhook endpoint handles streaming:

```
Vapi webhook → vapi_webhook.py → same graph.ainvoke → SSE stream (word by word)
```

The key insight: the same LangGraph graph works for both channels. Voice just adds a response length constraint via the system prompt.

---

## 13. Key Design Patterns Summary

### Pattern 1: Router → Specialist Agents

```
Cheap fast model (Haiku) routes to:
├─ Sonnet booking agent (complex multi-step)
├─ Sonnet RAG agent (knowledge retrieval)
└─ Sonnet cancellation agent (token verification)
```

Use a cheap model for classification; use the powerful model only where reasoning matters.

### Pattern 2: ReAct Loop (Reason + Act)

```
LLM reasons → decides to call tool → tool executes → LLM reasons with result → ...
```

Implemented via:
- `bind_tools()` — tells LLM what tools exist
- `ToolNode` — executes tool calls from LLM messages
- `_should_continue()` — checks `tool_calls` on last message to loop or end

### Pattern 3: Structured Extraction

```
Conversational LLM (tracks dialogue quality)
Extractor LLM (reads history → fills Pydantic model)
→ Extraction triggers direct booking path when all fields present
```

Separates "collecting information conversationally" from "parsing that information into structured form."

### Pattern 4: Direct Tool Calls for Critical Actions

```python
# Never: let LLM decide to call confirm_booking
# Always: agent code calls it directly after validating preconditions
result = await confirm_booking.ainvoke({...})
```

For irreversible actions (creating bookings, charging money, sending emails), remove the tool from LLM's tool list entirely. The agent logic makes the decision, not the LLM.

### Pattern 5: State as Single Source of Truth

```
booking_confirmed: True in state
    → all future turns in same session blocked
    → persisted in Postgres checkpointer
    → no way to re-book in same session regardless of what user says
```

LangGraph state is the authority. Don't replicate this logic in API middleware or the LLM prompt — put it in the node function where it's checkpointed.

### Pattern 6: Intent Preservation Mid-Flow

```python
# orchestrator_node:
if state.get("intent") == "book":
    if "cancel" in last_human.content.lower():
        return {"intent": "cancel"}
    return {"intent": "book"}   # skip LLM entirely
```

Once a user is mid-booking, short follow-up messages ("June 23", "John Smith", "yes that slot works") won't contain booking keywords. Without this guard, the router would misclassify them as FAQ and break the flow.

---

## Quick Reference: LangGraph vs Plain LangChain

| Need | Plain LangChain | LangGraph |
|------|----------------|-----------|
| Single LLM call | `llm.ainvoke(messages)` | same, inside a node |
| Multi-step with tools | manual loop | `ToolNode` + conditional edges |
| Multi-turn memory | manual history management | Checkpointer, `thread_id` |
| Multiple specialized agents | multiple `if` branches | graph nodes + conditional routing |
| Persistent state across turns | build it yourself | `add_messages` reducer + checkpoint |
| Complex branching logic | nested if/else | graph topology |

The rule of thumb: if your app needs more than 2 LLM calls in sequence, or needs multi-turn memory, use LangGraph. If it's a single call or simple pipeline, plain LangChain is enough.

---

*This document covers the complete LangChain/LangGraph surface of the booking bot. For external integrations (Google Calendar, Pinecone, Resend, Vapi), see the respective service files in `backend/services/`.*
