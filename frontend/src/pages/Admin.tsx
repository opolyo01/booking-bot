import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { format, parseISO } from "date-fns";
import { adminGetBookings, adminCancelBooking } from "@/api/client";
import type { Booking } from "@/types";

const MEETING_LABELS: Record<string, string> = {
  job_offer: "Job Offer",
  consulting: "Consulting",
  training: "Training",
  meetup_hackathon: "Meetup / Hackathon",
};

export function Admin() {
  const [searchParams] = useSearchParams();
  const [token, setToken] = useState<string | null>(null);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const t = searchParams.get("token");
    if (t) {
      setToken(t);
      localStorage.setItem("admin_token", t);
    } else {
      const stored = localStorage.getItem("admin_token");
      if (stored) setToken(stored);
    }
  }, [searchParams]);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    adminGetBookings(token)
      .then((data) => setBookings(data as Booking[]))
      .catch(() => setError("Failed to load bookings. Your session may have expired."))
      .finally(() => setLoading(false));
  }, [token]);

  const handleCancel = async (id: string) => {
    if (!token || !confirm("Cancel this booking?")) return;
    try {
      await adminCancelBooking(token, id);
      setBookings((prev) =>
        prev.map((b) => (b.id === id ? { ...b, status: "cancelled" } : b))
      );
    } catch {
      alert("Failed to cancel booking.");
    }
  };

  if (!token) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 mb-4">Admin</h1>
          <a
            href={`${import.meta.env.VITE_API_URL ?? ""}/auth/google`}
            className="inline-block bg-brand-500 text-white px-6 py-3 rounded-lg hover:bg-brand-600 transition-colors"
          >
            Sign in with Google
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Bookings</h1>
          <button
            onClick={() => { localStorage.removeItem("admin_token"); setToken(null); }}
            className="text-sm text-gray-500 hover:text-gray-700"
          >
            Sign out
          </button>
        </div>

        {loading && <p className="text-gray-500">Loading...</p>}
        {error && <p className="text-red-500">{error}</p>}

        {!loading && !error && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-100">
                <tr>
                  {["Name", "Email", "Type", "Time", "Status", ""].map((h) => (
                    <th key={h} className="px-4 py-3 text-left font-medium text-gray-600">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {bookings.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                      No bookings yet.
                    </td>
                  </tr>
                )}
                {bookings.map((b) => (
                  <tr key={b.id} className="border-b border-gray-50 hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium text-gray-800">{b.name}</td>
                    <td className="px-4 py-3 text-gray-600">{b.email}</td>
                    <td className="px-4 py-3 text-gray-600">
                      {MEETING_LABELS[b.meeting_type] ?? b.meeting_type}
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      {format(parseISO(b.start_time), "MMM d, HH:mm")}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
                          b.status === "confirmed"
                            ? "bg-green-100 text-green-700"
                            : "bg-gray-100 text-gray-500"
                        }`}
                      >
                        {b.status}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {b.status === "confirmed" && (
                        <button
                          onClick={() => handleCancel(b.id)}
                          className="text-red-500 hover:text-red-700 text-xs"
                        >
                          Cancel
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
