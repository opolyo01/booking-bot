from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from langchain_core.messages import HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.security import verify_cancel_token
from backend.db.database import get_db
from backend.db.models import BookingStatus
from backend.models.schemas import CancelResponse, ChatMessageIn, ChatMessageOut
from backend.services import booking_service, google_auth, google_calendar, redis_cache

router = APIRouter(tags=["booking"])


@router.post("/chat/message", response_model=ChatMessageOut)
async def chat_message(body: ChatMessageIn, request: Request):
    """Process a chat message through the LangGraph agent."""
    graph = request.app.state.graph

    config = {"configurable": {"thread_id": body.session_id}}
    # Only pass fields that change per-turn — let the checkpointer preserve
    # intent, booking_confirmed, and other collected state across turns.
    initial_state = {
        "messages": [HumanMessage(content=body.message)],
        "session_id": body.session_id,
        "channel": body.channel,
        "user_timezone": body.timezone or "UTC",
    }

    result = await graph.ainvoke(initial_state, config=config)

    last_ai_msg = next(
        (m for m in reversed(result["messages"]) if hasattr(m, "content") and not isinstance(m, HumanMessage) and not getattr(m, "tool_calls", None)),
        None,
    )
    reply = last_ai_msg.content if last_ai_msg else "I'm sorry, I couldn't process that."

    return ChatMessageOut(
        session_id=body.session_id,
        message=reply,
        booking_confirmed=result.get("booking_confirmed", False),
    )


@router.get("/slots")
async def get_slots(
    date: str = Query(..., description="YYYY-MM-DD"),
    meeting_type: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Return available booking slots (used by the frontend slot picker)."""
    from backend.tools.availability_tools import get_available_slots
    import json
    result = await get_available_slots.ainvoke({"date": date, "meeting_type": meeting_type})
    return json.loads(result)


@router.get("/cancel/{token}", response_model=CancelResponse)
async def cancel_booking(token: str, db: AsyncSession = Depends(get_db)):
    """Cancel a booking via the signed token from the confirmation email."""
    booking_id = verify_cancel_token(token)

    booking = await booking_service.get_booking_by_id(db, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.status == BookingStatus.cancelled:
        return CancelResponse(success=False, message="This booking is already cancelled.")

    creds = await google_auth.get_credentials(db)
    if creds and booking.google_event_id:
        try:
            await google_calendar.delete_event(creds, booking.google_event_id)
        except Exception:
            pass

    await booking_service.cancel_booking(db, booking)
    await redis_cache.invalidate_slots(booking.start_time.strftime("%Y-%m-%d"))

    from backend.services.resend_email import send_cancellation_confirmation
    await send_cancellation_confirmation(booking.email, booking.name)

    return CancelResponse(success=True, message="Your booking has been cancelled.")
