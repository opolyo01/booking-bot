import { format } from "date-fns";
import type { ChatMessage } from "@/types";

interface Props {
  message: ChatMessage;
}

export function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-3`}>
      {!isUser && (
        <div className="w-8 h-8 rounded-full bg-brand-500 flex items-center justify-center text-white text-xs font-bold mr-2 flex-shrink-0 mt-1">
          O
        </div>
      )}
      <div className="max-w-[75%]">
        <div
          className={`px-4 py-2.5 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
            isUser
              ? "bg-brand-500 text-white rounded-tr-sm"
              : "bg-gray-100 text-gray-800 rounded-tl-sm"
          }`}
        >
          {message.content}
        </div>
        <p className={`text-xs text-gray-400 mt-1 ${isUser ? "text-right" : "text-left"}`}>
          {format(message.timestamp, "HH:mm")}
        </p>
      </div>
    </div>
  );
}
