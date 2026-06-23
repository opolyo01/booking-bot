import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.agents.orchestrator import build_graph
from backend.core.config import get_settings
from backend.db.init_db import init_db
from backend.routers import admin, auth, booking, gmail, vapi_webhook
from backend.services.pinecone_service import ensure_index
from backend.services.redis_cache import close as close_redis

logger = logging.getLogger(__name__)


async def _send_reminders() -> None:
    """Send reminder emails for meetings starting in the next 24–25 hours."""
    from backend.db.database import AsyncSessionLocal
    from backend.db.models import BookingStatus
    from backend.services import booking_service, redis_cache, resend_email

    now = datetime.now(timezone.utc)
    window_start = now + timedelta(hours=24)
    window_end = now + timedelta(hours=25)

    async with AsyncSessionLocal() as db:
        bookings = await booking_service.get_confirmed_bookings_in_range(
            db, window_start, window_end
        )

    for b in bookings:
        if await redis_cache.was_reminder_sent(b.id):
            continue
        start_display = b.start_time.strftime("%A, %B %-d at %-I:%M %p UTC")
        await resend_email.send_reminder_email(
            to_email=b.email,
            name=b.name,
            meeting_type=b.meeting_type.value,
            start_time_str=start_display,
            cancel_token=b.cancel_token,
        )
        await redis_cache.mark_reminder_sent(b.id)
        logger.info("Reminder sent for booking %s (%s)", b.id, b.email)

settings = get_settings()


def _pg_conninfo() -> str:
    """Return a psycopg-compatible connection string (no driver prefix)."""
    url = settings.database_url
    for prefix in ("postgresql+asyncpg://", "postgres+asyncpg://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    ensure_index()

    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from psycopg_pool import AsyncConnectionPool
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    async with AsyncConnectionPool(
        conninfo=_pg_conninfo(),
        max_size=10,
        kwargs={"autocommit": True},
    ) as pool:
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()  # creates checkpoint tables if not exist
        app.state.graph = build_graph(checkpointer=checkpointer)

        scheduler = AsyncIOScheduler()
        scheduler.add_job(_send_reminders, "interval", minutes=30, id="reminders")
        scheduler.start()

        yield

        scheduler.shutdown(wait=False)

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
app.include_router(gmail.router)
app.include_router(vapi_webhook.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
