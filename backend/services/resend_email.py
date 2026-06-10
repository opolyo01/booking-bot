import asyncio
import logging

import resend

from backend.core.config import get_settings

settings = get_settings()
resend.api_key = settings.resend_api_key

logger = logging.getLogger(__name__)


def _cancel_url(cancel_token: str) -> str:
    return f"{settings.frontend_url}/cancel/{cancel_token}"


async def send_booking_confirmation(
    to_email: str,
    name: str,
    meeting_type: str,
    start_time_str: str,
    cancel_token: str,
    topic: str = "",
) -> None:
    topic_line = f"<p><strong>Topic:</strong> {topic}</p>" if topic else ""
    label = meeting_type.replace("_", " ").title()

    def _sync():
        resend.Emails.send({
            "from": settings.from_email,
            "to": [to_email],
            "subject": f"Booking confirmed — {label} with Oleg",
            "html": f"""
            <h2>Your booking is confirmed!</h2>
            <p>Hi {name},</p>
            <p>Your <strong>{label}</strong> meeting has been scheduled
               for <strong>{start_time_str}</strong>.</p>
            {topic_line}
            <p>You'll receive a Google Calendar invite shortly.</p>
            <hr/>
            <p style="font-size:12px;color:#666;">
              Need to cancel?
              <a href="{_cancel_url(cancel_token)}">Click here</a>
              (link valid for 30 days).
            </p>
            """,
        })

    try:
        await asyncio.to_thread(_sync)
        logger.info("Confirmation email sent to %s", to_email)
    except Exception as e:
        logger.warning("Failed to send confirmation email to %s: %s", to_email, e)


async def send_cancellation_confirmation(to_email: str, name: str) -> None:
    def _sync():
        resend.Emails.send({
            "from": settings.from_email,
            "to": [to_email],
            "subject": "Booking cancelled",
            "html": f"""
            <h2>Booking cancelled</h2>
            <p>Hi {name}, your appointment has been successfully cancelled.</p>
            <p>Feel free to
               <a href="{settings.frontend_url}">book a new time</a>
               whenever you're ready.</p>
            """,
        })

    try:
        await asyncio.to_thread(_sync)
    except Exception as e:
        logger.warning("Failed to send cancellation email to %s: %s", to_email, e)
