import logging
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.agents.orchestrator import build_graph
from backend.core.config import get_settings
from backend.db.init_db import init_db
from backend.routers import admin, auth, booking, vapi_webhook
from backend.services.pinecone_service import ensure_index
from backend.services.redis_cache import close as close_redis

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    ensure_index()

    # LangGraph graph with in-memory checkpointer
    # For production, swap MemorySaver for AsyncPostgresSaver or AsyncRedisSaver
    from langgraph.checkpoint.memory import MemorySaver
    checkpointer = MemorySaver()
    app.state.graph = build_graph(checkpointer=checkpointer)

    yield

    await close_redis()


app = FastAPI(
    title="Booking Bot API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(booking.router)
app.include_router(admin.router)
app.include_router(vapi_webhook.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
