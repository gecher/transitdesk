export type Status = "CONFIRMED" | "PENDING" | "CANCELLED";
export const STATUSES: Status[] = ["CONFIRMED", "PENDING", "CANCELLED"];

export interface Booking {
  ref: string;
  passenger: string;
  hotel: string;
  night: string;
  status: Status;
  pickup_time: string | null;
  onward_flight: string | null;
}

export interface Hotel {
  name: string;
  location: string;
  shuttle: string;
  phone: string;
  bookings?: number;
}

export interface Approval {
  thread_id: string;
  booking_ref: string;
  passenger: string;
  hotel: string;
  night: string;
  passenger_message: string;
  warning: string;
}

/** One tool call the agent made, and what the tool returned. */
export interface Lookup {
  name: string;
  args: Record<string, unknown>;
  result?: string;
}

export interface ChatMessage {
  id: number;
  role: "you" | "desk" | "note";
  text: string;
  lookups?: Lookup[];
  meta?: string;
}

/** Events streamed by POST /chat, one JSON object per line. */
export type StreamEvent =
  | { type: "node"; node: string }
  | { type: "token"; text: string }
  | { type: "tool_call"; name: string; args: Record<string, unknown> }
  | { type: "tool_result"; name: string; content: string }
  | { type: "approval_needed"; booking_ref: string }
  | { type: "done"; category: string; booking_ref: string | null; reply: string; streamed: boolean }
  | { type: "error"; message: string };

export interface ThreadInfo {
  booking_ref: string | null;
  waiting_for_approval: boolean;
  messages: { role: string; text: string }[];
}
