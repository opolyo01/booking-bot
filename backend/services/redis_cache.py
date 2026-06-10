import json
from typing import Optional

import redis.asyncio as aioredis

from backend.core.config import get_settings

settings = get_settings()

_client: Optional[aioredis.Redis] = None


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _client


# Calendar slot cache — TTL 10 minutes
_SLOTS_TTL = 600
_SLOTS_PREFIX = "slots:"


async def get_cached_slots(date_str: str, meeting_type: str) -> Optional[list[dict]]:
    key = f"{_SLOTS_PREFIX}{date_str}:{meeting_type}"
    raw = await get_redis().get(key)
    return json.loads(raw) if raw else None


async def cache_slots(date_str: str, meeting_type: str, slots: list[dict]) -> None:
    key = f"{_SLOTS_PREFIX}{date_str}:{meeting_type}"
    await get_redis().setex(key, _SLOTS_TTL, json.dumps(slots))


async def invalidate_slots(date_str: str) -> None:
    pattern = f"{_SLOTS_PREFIX}{date_str}:*"
    keys = await get_redis().keys(pattern)
    if keys:
        await get_redis().delete(*keys)


# Conversation state — used by the Vapi voice channel for session persistence
_SESSION_TTL = 3600  # 1 hour
_SESSION_PREFIX = "session:"


async def get_session_state(session_id: str) -> Optional[dict]:
    raw = await get_redis().get(f"{_SESSION_PREFIX}{session_id}")
    return json.loads(raw) if raw else None


async def save_session_state(session_id: str, state: dict) -> None:
    await get_redis().setex(
        f"{_SESSION_PREFIX}{session_id}", _SESSION_TTL, json.dumps(state)
    )


# Reminder tracking — prevent duplicate reminder emails
_REMINDER_TTL = 7 * 24 * 3600  # 7 days
_REMINDER_PREFIX = "reminder_sent:"


async def was_reminder_sent(booking_id: str) -> bool:
    return bool(await get_redis().get(f"{_REMINDER_PREFIX}{booking_id}"))


async def mark_reminder_sent(booking_id: str) -> None:
    await get_redis().setex(f"{_REMINDER_PREFIX}{booking_id}", _REMINDER_TTL, "1")


async def close() -> None:
    global _client
    if _client:
        await _client.aclose()
        _client = None
