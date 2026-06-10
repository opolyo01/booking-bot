from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.security import create_cancel_token
from backend.db.models import Booking, BookingStatus, MeetingTypeConfig, MeetingTypeEnum, OfficeHours


async def get_office_hours(db: AsyncSession) -> list[OfficeHours]:
    result = await db.execute(
        select(OfficeHours).where(OfficeHours.is_active.is_(True))
    )
    return list(result.scalars().all())


async def get_meeting_type_config(
    db: AsyncSession, meeting_type: MeetingTypeEnum
) -> Optional[MeetingTypeConfig]:
    result = await db.execute(
        select(MeetingTypeConfig).where(
            MeetingTypeConfig.meeting_type == meeting_type,
            MeetingTypeConfig.is_active.is_(True),
        )
    )
    return result.scalars().first()


async def get_confirmed_bookings_in_range(
    db: AsyncSession, start: datetime, end: datetime
) -> list[Booking]:
    result = await db.execute(
        select(Booking).where(
            Booking.status == BookingStatus.confirmed,
            Booking.start_time < end,
            Booking.end_time > start,
        )
    )
    return list(result.scalars().all())


def compute_available_slots(
    date: datetime,
    office_hours: list[OfficeHours],
    busy_intervals: list[dict],   # [{"start": iso_str, "end": iso_str}, ...]
    duration_minutes: int,
    buffer_minutes: int = 15,
    min_notice_hours: int = 2,
) -> list[dict]:
    """Returns list of {"start": datetime, "end": datetime} dicts in UTC."""
    day_of_week = date.weekday()
    oh = next((o for o in office_hours if o.day_of_week == day_of_week), None)
    if not oh:
        return []

    day_start = date.replace(
        hour=oh.start_time.hour,
        minute=oh.start_time.minute,
        second=0,
        microsecond=0,
        tzinfo=timezone.utc,
    )
    day_end = date.replace(
        hour=oh.end_time.hour,
        minute=oh.end_time.minute,
        second=0,
        microsecond=0,
        tzinfo=timezone.utc,
    )

    earliest_bookable = datetime.now(timezone.utc) + timedelta(hours=min_notice_hours)

    # Merge all busy periods (existing bookings + Google Calendar)
    blocked: list[tuple[datetime, datetime]] = []
    for interval in busy_intervals:
        s = datetime.fromisoformat(interval["start"].replace("Z", "+00:00"))
        e = datetime.fromisoformat(interval["end"].replace("Z", "+00:00"))
        blocked.append((s, e))
    blocked.sort()

    slots: list[dict] = []
    cursor = max(day_start, earliest_bookable)
    slot_duration = timedelta(minutes=duration_minutes)
    total_duration = timedelta(minutes=duration_minutes + buffer_minutes)

    while cursor + slot_duration <= day_end:
        slot_end = cursor + slot_duration
        conflict = any(s < slot_end and e > cursor for s, e in blocked)
        if not conflict:
            slots.append({"start": cursor, "end": slot_end})
            cursor += total_duration
        else:
            # Advance past the conflicting block
            overlap = next((e for s, e in blocked if s < slot_end and e > cursor), None)
            cursor = overlap if overlap else cursor + timedelta(minutes=15)

    return slots


async def create_booking(
    db: AsyncSession,
    name: str,
    email: str,
    meeting_type: MeetingTypeEnum,
    start_time: datetime,
    end_time: datetime,
    tz: str,
    topic: Optional[str] = None,
    google_event_id: Optional[str] = None,
) -> Booking:
    booking = Booking(
        name=name,
        email=email,
        meeting_type=meeting_type,
        start_time=start_time,
        end_time=end_time,
        timezone=tz,
        topic=topic,
        google_event_id=google_event_id,
        cancel_token="placeholder",
    )
    db.add(booking)
    await db.flush()  # populate booking.id

    booking.cancel_token = create_cancel_token(booking.id)
    await db.commit()
    await db.refresh(booking)
    return booking


async def cancel_booking(db: AsyncSession, booking: Booking) -> None:
    booking.status = BookingStatus.cancelled
    await db.commit()


async def get_booking_by_id(db: AsyncSession, booking_id: str) -> Optional[Booking]:
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    return result.scalars().first()


async def list_bookings(
    db: AsyncSession,
    status: Optional[BookingStatus] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Booking]:
    q = select(Booking).order_by(Booking.start_time.desc()).limit(limit).offset(offset)
    if status:
        q = q.where(Booking.status == status)
    result = await db.execute(q)
    return list(result.scalars().all())
