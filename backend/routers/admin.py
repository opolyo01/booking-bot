from datetime import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.security import get_current_admin
from backend.db.database import get_db
from backend.db.models import BookingStatus, MeetingTypeConfig, MeetingTypeEnum, OfficeHours
from backend.models.schemas import (
    BookingOut,
    MeetingTypeConfigOut,
    MeetingTypeConfigUpdate,
    OfficeHoursOut,
    OfficeHoursUpdate,
)
from backend.services.booking_service import (
    cancel_booking,
    get_booking_by_id,
    list_bookings,
)
from backend.services import google_auth, google_calendar

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Bookings ──────────────────────────────────────────────────────────────────

@router.get("/bookings", response_model=list[BookingOut])
async def admin_list_bookings(
    status: BookingStatus = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
):
    return await list_bookings(db, status=status, limit=limit, offset=offset)


@router.get("/bookings/{booking_id}", response_model=BookingOut)
async def admin_get_booking(
    booking_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
):
    booking = await get_booking_by_id(db, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


@router.delete("/bookings/{booking_id}")
async def admin_cancel_booking(
    booking_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
):
    booking = await get_booking_by_id(db, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.status == BookingStatus.cancelled:
        raise HTTPException(status_code=400, detail="Already cancelled")

    creds = await google_auth.get_credentials(db)
    if creds and booking.google_event_id:
        try:
            await google_calendar.delete_event(creds, booking.google_event_id)
        except Exception:
            pass

    await cancel_booking(db, booking)
    return {"success": True}


# ── Office hours ──────────────────────────────────────────────────────────────

@router.get("/office-hours", response_model=list[OfficeHoursOut])
async def admin_get_office_hours(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
):
    result = await db.execute(select(OfficeHours).order_by(OfficeHours.day_of_week))
    return list(result.scalars().all())


@router.put("/office-hours")
async def admin_update_office_hours(
    updates: list[OfficeHoursUpdate],
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
):
    result = await db.execute(select(OfficeHours))
    existing = {o.day_of_week: o for o in result.scalars().all()}

    for update in updates:
        start_h, start_m = map(int, update.start_time.split(":"))
        end_h, end_m = map(int, update.end_time.split(":"))
        if update.day_of_week in existing:
            record = existing[update.day_of_week]
            record.start_time = time(start_h, start_m)
            record.end_time = time(end_h, end_m)
            record.is_active = update.is_active
        else:
            db.add(
                OfficeHours(
                    day_of_week=update.day_of_week,
                    start_time=time(start_h, start_m),
                    end_time=time(end_h, end_m),
                    is_active=update.is_active,
                )
            )

    await db.commit()
    return {"success": True}


# ── Meeting type config ───────────────────────────────────────────────────────

@router.get("/meeting-types", response_model=list[MeetingTypeConfigOut])
async def admin_list_meeting_types(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
):
    result = await db.execute(select(MeetingTypeConfig))
    return list(result.scalars().all())


@router.put("/meeting-types/{meeting_type}", response_model=MeetingTypeConfigOut)
async def admin_update_meeting_type(
    meeting_type: MeetingTypeEnum,
    update: MeetingTypeConfigUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
):
    result = await db.execute(
        select(MeetingTypeConfig).where(MeetingTypeConfig.meeting_type == meeting_type)
    )
    config = result.scalars().first()
    if not config:
        raise HTTPException(status_code=404, detail="Meeting type not found")

    config.duration_minutes = update.duration_minutes
    config.description = update.description
    config.is_active = update.is_active
    await db.commit()
    await db.refresh(config)
    return config
