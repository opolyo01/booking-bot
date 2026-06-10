from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr

from backend.db.models import BookingStatus, MeetingTypeEnum


# ── Chat ──────────────────────────────────────────────────────────────────────

class ChatMessageIn(BaseModel):
    session_id: str
    message: str
    channel: str = "web"  # "web" | "voice"
    timezone: Optional[str] = None


class ChatMessageOut(BaseModel):
    session_id: str
    message: str
    booking_confirmed: bool = False


# ── Bookings ──────────────────────────────────────────────────────────────────

class BookingOut(BaseModel):
    id: str
    name: str
    email: str
    meeting_type: MeetingTypeEnum
    topic: Optional[str]
    start_time: datetime
    end_time: datetime
    timezone: str
    status: BookingStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class SlotOut(BaseModel):
    start: datetime
    end: datetime


class CancelResponse(BaseModel):
    success: bool
    message: str


# ── Office hours ──────────────────────────────────────────────────────────────

class OfficeHoursOut(BaseModel):
    id: int
    day_of_week: int
    start_time: str
    end_time: str
    is_active: bool

    model_config = {"from_attributes": True}


class OfficeHoursUpdate(BaseModel):
    day_of_week: int
    start_time: str   # "HH:MM"
    end_time: str     # "HH:MM"
    is_active: bool


# ── Meeting type config ───────────────────────────────────────────────────────

class MeetingTypeConfigOut(BaseModel):
    id: str
    meeting_type: MeetingTypeEnum
    duration_minutes: int
    description: Optional[str]
    is_active: bool

    model_config = {"from_attributes": True}


class MeetingTypeConfigUpdate(BaseModel):
    duration_minutes: int
    description: Optional[str] = None
    is_active: bool = True
