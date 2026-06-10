export type Channel = "web" | "voice";

export type MeetingType =
  | "job_offer"
  | "consulting"
  | "training"
  | "meetup_hackathon";

export type BookingStatus = "confirmed" | "cancelled";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

export interface Slot {
  start: string; // ISO 8601
  end: string;
}

export interface Booking {
  id: string;
  name: string;
  email: string;
  meeting_type: MeetingType;
  topic?: string;
  start_time: string;
  end_time: string;
  timezone: string;
  status: BookingStatus;
  created_at: string;
}

export interface MeetingTypeConfig {
  id: string;
  meeting_type: MeetingType;
  duration_minutes: number;
  description?: string;
  is_active: boolean;
}

export interface OfficeHours {
  id: number;
  day_of_week: number;
  start_time: string;
  end_time: string;
  is_active: boolean;
}
