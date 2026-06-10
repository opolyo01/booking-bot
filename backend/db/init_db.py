from datetime import time

from sqlalchemy import select

from backend.db.database import AsyncSessionLocal, engine
from backend.db.models import Base, MeetingTypeConfig, MeetingTypeEnum, OfficeHours


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(OfficeHours))
        if result.scalars().first():
            return  # already seeded

        for day in range(5):  # Monday–Friday
            db.add(OfficeHours(day_of_week=day, start_time=time(10, 0), end_time=time(18, 0)))

        meeting_defaults = [
            MeetingTypeConfig(
                meeting_type=MeetingTypeEnum.job_offer,
                duration_minutes=30,
                description="Discuss job offers and career opportunities.",
            ),
            MeetingTypeConfig(
                meeting_type=MeetingTypeEnum.consulting,
                duration_minutes=30,
                description="Consulting engagements and project scoping.",
            ),
            MeetingTypeConfig(
                meeting_type=MeetingTypeEnum.training,
                duration_minutes=30,
                description="Training programs, workshops, and learning proposals.",
            ),
            MeetingTypeConfig(
                meeting_type=MeetingTypeEnum.meetup_hackathon,
                duration_minutes=15,
                description="Meetups, hackathons, and community events.",
            ),
        ]
        db.add_all(meeting_defaults)
        await db.commit()
