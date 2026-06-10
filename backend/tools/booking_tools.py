import json
from datetime import datetime, timezone

from langchain_core.tools import tool

from backend.db.database import AsyncSessionLocal
from backend.db.models import MeetingTypeEnum
from backend.services import booking_service, google_auth, google_calendar, redis_cache, resend_email


@tool
async def confirm_booking(
    name: str,
    email: str,
    meeting_type: str,
    slot_start: str,
    user_timezone: str,
    topic: str = "",
) -> str:
    """
    Create a confirmed booking, add to Google Calendar, and send a confirmation email.

    Args:
        name: Full name of the person booking.
        email: Email address of the person booking.
        meeting_type: One of job_offer, consulting, training, meetup_hackathon.
        slot_start: ISO 8601 datetime string for the start of the slot (UTC).
        user_timezone: IANA timezone string of the booker (e.g. "America/New_York").
        topic: Optional brief description of the meeting topic.

    Returns:
        JSON with booking_id and cancel_token on success, or error message.
    """
    try:
        mt_enum = MeetingTypeEnum(meeting_type)
    except ValueError:
        return json.dumps({"error": f"Unknown meeting type: {meeting_type}"})

    start = datetime.fromisoformat(slot_start.replace("Z", "+00:00"))
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)

    async with AsyncSessionLocal() as db:
        config = await booking_service.get_meeting_type_config(db, mt_enum)
        if not config:
            return json.dumps({"error": "Meeting type not available"})

        from datetime import timedelta
        end = start + timedelta(minutes=config.duration_minutes)

        creds = await google_auth.get_credentials(db)
        google_event_id = None
        if creds:
            summary = f"{mt_enum.value.replace('_', ' ').title()} — {name}"
            description = f"Booked via Booking Bot\nTopic: {topic}" if topic else "Booked via Booking Bot"
            google_event_id = await google_calendar.create_event(
                creds=creds,
                summary=summary,
                description=description,
                start_time=start,
                end_time=end,
                attendee_email=email,
                tz=user_timezone,
            )

        booking = await booking_service.create_booking(
            db=db,
            name=name,
            email=email,
            meeting_type=mt_enum,
            start_time=start,
            end_time=end,
            tz=user_timezone,
            topic=topic or None,
            google_event_id=google_event_id,
        )

    # Invalidate slot cache for this date
    await redis_cache.invalidate_slots(start.strftime("%Y-%m-%d"))

    start_display = start.strftime("%A, %B %-d at %-I:%M %p UTC")
    try:
        await resend_email.send_booking_confirmation(
            to_email=email,
            name=name,
            meeting_type=meeting_type,
            start_time_str=start_display,
            cancel_token=booking.cancel_token,
            topic=topic,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Confirmation email failed (booking still created): %s", e)

    return json.dumps({
        "booking_id": booking.id,
        "cancel_token": booking.cancel_token,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "meeting_type": meeting_type,
    })


@tool
async def cancel_booking_by_token(cancel_token: str) -> str:
    """
    Cancel a booking using its cancellation token.

    Args:
        cancel_token: The JWT cancellation token from the confirmation email.

    Returns:
        Success message or error.
    """
    from backend.core.security import verify_cancel_token
    from fastapi import HTTPException

    try:
        booking_id = verify_cancel_token(cancel_token)
    except HTTPException as exc:
        return json.dumps({"error": exc.detail})

    async with AsyncSessionLocal() as db:
        booking = await booking_service.get_booking_by_id(db, booking_id)
        if not booking:
            return json.dumps({"error": "Booking not found"})
        if booking.status.value == "cancelled":
            return json.dumps({"error": "Booking is already cancelled"})

        creds = await google_auth.get_credentials(db)
        if creds and booking.google_event_id:
            try:
                await google_calendar.delete_event(creds, booking.google_event_id)
            except Exception:
                pass  # best-effort; proceed with DB cancellation

        await booking_service.cancel_booking(db, booking)
        await resend_email.send_cancellation_confirmation(booking.email, booking.name)

    await redis_cache.invalidate_slots(booking.start_time.strftime("%Y-%m-%d"))
    return json.dumps({
        "success": True,
        "booking_id": booking_id,
        "name": booking.name,
        "email": booking.email,
        "meeting_type": booking.meeting_type.value,
        "old_start": booking.start_time.isoformat(),
    })
