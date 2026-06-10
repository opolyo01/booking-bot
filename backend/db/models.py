import enum
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    Integer,
    String,
    Text,
    Time,
)
from sqlalchemy.sql import func

from backend.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class MeetingTypeEnum(str, enum.Enum):
    job_offer = "job_offer"
    consulting = "consulting"
    training = "training"
    meetup_hackathon = "meetup_hackathon"


class BookingStatus(str, enum.Enum):
    confirmed = "confirmed"
    cancelled = "cancelled"


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    meeting_type = Column(SQLEnum(MeetingTypeEnum), nullable=False)
    topic = Column(Text, nullable=True)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    timezone = Column(String(50), nullable=False, default="UTC")
    cancel_token = Column(String(512), unique=True, nullable=False)
    google_event_id = Column(String(255), nullable=True)
    status = Column(SQLEnum(BookingStatus), default=BookingStatus.confirmed, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OfficeHours(Base):
    __tablename__ = "office_hours"

    id = Column(Integer, primary_key=True, autoincrement=True)
    day_of_week = Column(Integer, nullable=False)  # 0=Monday … 6=Sunday
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)


class MeetingTypeConfig(Base):
    __tablename__ = "meeting_type_configs"

    id = Column(String, primary_key=True, default=_uuid)
    meeting_type = Column(SQLEnum(MeetingTypeEnum), unique=True, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)


class OAuthToken(Base):
    """Stores the owner's Google OAuth tokens for server-side calendar access."""

    __tablename__ = "oauth_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String(50), nullable=False, default="google")
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=False)
    token_expiry = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
