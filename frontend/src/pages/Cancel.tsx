import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { cancelBooking } from "@/api/client";

export function Cancel() {
  const { token } = useParams<{ token: string }>();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setMessage("Invalid cancellation link.");
      return;
    }
    cancelBooking(token)
      .then((res) => {
        setStatus(res.success ? "success" : "error");
        setMessage(res.message);
      })
      .catch(() => {
        setStatus("error");
        setMessage("Could not cancel — the link may be expired or already used.");
      });
  }, [token]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-brand-50 to-white flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-lg p-8 max-w-md w-full text-center">
        {status === "loading" && (
          <>
            <div className="w-12 h-12 border-4 border-brand-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            <p className="text-gray-600">Cancelling your booking...</p>
          </>
        )}
        {status === "success" && (
          <>
            <div className="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-6 h-6 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Booking Cancelled</h2>
            <p className="text-gray-500 text-sm">{message}</p>
            <a href="/" className="mt-6 inline-block text-brand-500 hover:underline text-sm">
              Book a new time
            </a>
          </>
        )}
        {status === "error" && (
          <>
            <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-6 h-6 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Cancellation Failed</h2>
            <p className="text-gray-500 text-sm">{message}</p>
          </>
        )}
      </div>
    </div>
  );
}
