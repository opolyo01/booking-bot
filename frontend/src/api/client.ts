const BASE = import.meta.env.VITE_API_URL ?? "";

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ── Chat ──────────────────────────────────────────────────────────────────────

export async function sendChatMessage(
  sessionId: string,
  message: string,
  timezone: string
): Promise<{ session_id: string; message: string; booking_confirmed: boolean }> {
  return request("/chat/message", {
    method: "POST",
    body: JSON.stringify({
      session_id: sessionId,
      message,
      channel: "web",
      timezone,
    }),
  });
}

// ── Slots ─────────────────────────────────────────────────────────────────────

export async function getSlots(
  date: string,
  meetingType: string
): Promise<{ start: string; end: string }[]> {
  return request(`/slots?date=${date}&meeting_type=${meetingType}`);
}

// ── Cancel ───────────────────────────────────────────────────────────────────

export async function cancelBooking(
  token: string
): Promise<{ success: boolean; message: string }> {
  return request(`/cancel/${token}`);
}

// ── Admin (all require JWT token) ─────────────────────────────────────────────

export async function adminGetBookings(token: string) {
  return request("/admin/bookings", {}, token);
}

export async function adminCancelBooking(token: string, id: string) {
  return request(`/admin/bookings/${id}`, { method: "DELETE" }, token);
}

export async function adminGetOfficeHours(token: string) {
  return request("/admin/office-hours", {}, token);
}

export async function adminUpdateOfficeHours(token: string, payload: unknown) {
  return request("/admin/office-hours", {
    method: "PUT",
    body: JSON.stringify(payload),
  }, token);
}

export async function adminGetMeetingTypes(token: string) {
  return request("/admin/meeting-types", {}, token);
}

export async function adminUpdateMeetingType(
  token: string,
  meetingType: string,
  payload: unknown
) {
  return request(`/admin/meeting-types/${meetingType}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  }, token);
}
