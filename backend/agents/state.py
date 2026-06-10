from typing import Annotated, Literal, Optional

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class ConversationState(TypedDict):
    messages: Annotated[list, add_messages]
    session_id: str
    channel: Literal["web", "voice"]

    # Classified intent for the current conversation turn
    intent: Optional[Literal["book", "faq", "cancel", "unknown"]]

    # Collected booking info
    user_name: Optional[str]
    user_email: Optional[str]
    user_timezone: Optional[str]
    meeting_type: Optional[str]
    topic: Optional[str]
    available_slots: Optional[list[str]]
    selected_slot: Optional[str]

    # Set after a booking is successfully created
    booking_id: Optional[str]
    cancel_token: Optional[str]
    booking_confirmed: bool

    # Passed in when user provides a cancellation token via chat
    cancel_token_input: Optional[str]

    error_message: Optional[str]
