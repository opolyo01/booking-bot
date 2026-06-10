import { ChatWidget } from "@/components/ChatWidget";

export function Home() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-brand-50 to-white flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Book a Meeting</h1>
          <p className="text-gray-500 text-sm mt-1">
            Chat with Oleg's AI assistant to schedule a time
          </p>
        </div>
        <div className="h-[600px]">
          <ChatWidget />
        </div>
        {import.meta.env.VITE_VAPI_PHONE_NUMBER && (
          <p className="text-center text-xs text-gray-400 mt-4">
            Prefer a call?{" "}
            <a
              href={`tel:${import.meta.env.VITE_VAPI_PHONE_NUMBER}`}
              className="text-brand-500 hover:underline font-medium"
            >
              {import.meta.env.VITE_VAPI_PHONE_NUMBER}
            </a>
          </p>
        )}
      </div>
    </div>
  );
}
