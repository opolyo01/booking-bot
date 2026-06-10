import asyncio
from datetime import datetime

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from backend.core.config import get_settings

settings = get_settings()


def _service(creds: Credentials):
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


async def get_busy_slots(
    creds: Credentials,
    time_min: datetime,
    time_max: datetime,
) -> list[dict]:
    def _sync():
        svc = _service(creds)
        result = svc.freebusy().query(body={
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "items": [{"id": settings.google_calendar_id}],
        }).execute()
        return (
            result.get("calendars", {})
            .get(settings.google_calendar_id, {})
            .get("busy", [])
        )

    return await asyncio.to_thread(_sync)


async def create_event(
    creds: Credentials,
    summary: str,
    description: str,
    start_time: datetime,
    end_time: datetime,
    attendee_email: str,
    tz: str = "UTC",
) -> str:
    def _sync():
        svc = _service(creds)
        event = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start_time.isoformat(), "timeZone": tz},
            "end": {"dateTime": end_time.isoformat(), "timeZone": tz},
            "attendees": [{"email": attendee_email}],
            "reminders": {
                "useDefault": False,
                "overrides": [{"method": "email", "minutes": 60}],
            },
        }
        return (
            svc.events()
            .insert(
                calendarId=settings.google_calendar_id,
                body=event,
                sendUpdates="all",
            )
            .execute()["id"]
        )

    return await asyncio.to_thread(_sync)


async def delete_event(creds: Credentials, event_id: str) -> None:
    def _sync():
        svc = _service(creds)
        svc.events().delete(
            calendarId=settings.google_calendar_id,
            eventId=event_id,
            sendUpdates="all",
        ).execute()

    await asyncio.to_thread(_sync)
