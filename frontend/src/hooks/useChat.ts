import { useCallback, useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";
import { sendChatMessage } from "@/api/client";
import type { ChatMessage } from "@/types";

function getSessionId(): string {
  const key = "booking_session_id";
  let id = sessionStorage.getItem(key);
  if (!id) {
    id = uuidv4();
    sessionStorage.setItem(key, id);
  }
  return id;
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Hi! I'm Oleg's scheduling assistant. I can help you book a meeting, answer questions about Oleg, or help with cancellations. What can I do for you?",
      timestamp: new Date(),
    },
  ]);
  const [loading, setLoading] = useState(false);
  const [bookingConfirmed, setBookingConfirmed] = useState(false);
  const sessionId = useRef(getSessionId());

  const sendMessage = useCallback(async (text: string) => {
    const userMsg: ChatMessage = {
      id: uuidv4(),
      role: "user",
      content: text,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
      const res = await sendChatMessage(sessionId.current, text, tz);

      const aiMsg: ChatMessage = {
        id: uuidv4(),
        role: "assistant",
        content: res.message,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, aiMsg]);
      if (res.booking_confirmed) setBookingConfirmed(true);
    } catch (err) {
      const errMsg: ChatMessage = {
        id: uuidv4(),
        role: "assistant",
        content: "Sorry, something went wrong. Please try again.",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setLoading(false);
    }
  }, []);

  return { messages, loading, bookingConfirmed, sendMessage };
}
