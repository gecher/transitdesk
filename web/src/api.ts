import type { StreamEvent, ThreadInfo } from "./types";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

/** FastAPI errors are either a string or a list of validation problems. */
async function errorDetail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail.map((d: { msg: string }) => d.msg.replace("Value error, ", "")).join("; ");
    }
  } catch {
    /* not JSON */
  }
  return res.statusText || `Error ${res.status}`;
}

/** JSON request to the staff API. The staff key travels in a header. */
export async function api<T>(path: string, staffKey: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", "X-Staff-Key": staffKey },
  });
  if (!res.ok) throw new ApiError(await errorDetail(res), res.status);
  return res.json() as Promise<T>;
}

/** Send a passenger message and call onEvent for every streamed event (NDJSON). */
export async function streamChat(
  threadId: string,
  message: string,
  onEvent: (e: StreamEvent) => void,
): Promise<void> {
  const res = await fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thread_id: threadId, message }),
  });
  if (!res.ok || !res.body) throw new ApiError(await errorDetail(res), res.status);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";            // keep an unfinished line for the next chunk
    for (const line of lines) if (line.trim()) onEvent(JSON.parse(line) as StreamEvent);
  }
}

export async function getThread(threadId: string): Promise<ThreadInfo> {
  const res = await fetch("/threads/" + encodeURIComponent(threadId));
  if (!res.ok) throw new ApiError(await errorDetail(res), res.status);
  return res.json();
}

export async function getConfig(): Promise<{ public_read: boolean }> {
  const res = await fetch("/config");
  return res.ok ? res.json() : { public_read: false };
}

/** Hard to guess: anyone who knows a thread id can read that conversation. */
export function newThreadId(): string {
  const bytes = new Uint8Array(8);
  crypto.getRandomValues(bytes);
  return "web-" + Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}
