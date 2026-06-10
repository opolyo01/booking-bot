import json
from datetime import datetime, timezone

from langchain_core.tools import tool

from backend.db.database import AsyncSessionLocal
from backend.db.models import MeetingTypeEnum
from backend.services import booking_service, google_auth, google_calendar, redis_cache


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
    from dateutil import parser as dateutil_parser

    try:
        target_date = dateutil_parser.parse(date, default=datetime.now()).replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError):
        return json.dumps({"error": f"Could not parse date '{date}'. Try 'June 23' or '2026-06-23'."})

    try:
        mt_enum = MeetingTypeEnum(meeting_type)
    except ValueError:
        return json.dumps({"error": f"Unknown meeting type: {meeting_type}"})

    day_start = target_date.replace(hour=0, minute=0, second=0)
    day_end = target_date.replace(hour=23, minute=59, second=59)

    async with AsyncSessionLocal() as db:
        config = await booking_service.get_meeting_type_config(db, mt_enum)
        if not config:
            return json.dumps({"error": "Meeting type not available"})

        office_hours = await booking_service.get_office_hours(db)

        db_bookings = await booking_service.get_confirmed_bookings_in_range(
            db, day_start, day_end
        )
        busy_from_db = [
            {"start": b.start_time.isoformat(), "end": b.end_time.isoformat()}
            for b in db_bookings
        ]

        creds = await google_auth.get_credentials(db)
        busy_from_gcal: list[dict] = []
        if creds:
            busy_from_gcal = await google_calendar.get_busy_slots(
                creds, day_start, day_end
            )

        slots = booking_service.compute_available_slots(
            date=target_date,
            office_hours=office_hours,
            busy_intervals=busy_from_db + busy_from_gcal,
            duration_minutes=config.duration_minutes,
        )

    result = [
        {"start": s["start"].isoformat(), "end": s["end"].isoformat()} for s in slots
    ]
    await redis_cache.cache_slots(date, meeting_type, result)

    response: dict = {"slots": result}

    if preferred_time and result:
        try:
            pref_dt = dateutil_parser.parse(
                f"{target_date.date()} {preferred_time}", default=target_date
            ).replace(tzinfo=timezone.utc)
            nearest = min(
                result,
                key=lambda s: abs((datetime.fromisoformat(s["start"]) - pref_dt).total_seconds()),
            )
            response["suggested_slot"] = nearest
        except Exception:
            pass

    return json.dumps(response)
