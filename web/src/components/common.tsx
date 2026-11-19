import type { Status } from "../types";

export function StatusPill({ status }: { status: Status }) {
  return <span className={`status ${status}`}>{status.charAt(0) + status.slice(1).toLowerCase()}</span>;
}

export function Locked({ text }: { text?: string }) {
  return (
    <div className="locked">
      <p>{text ?? "Enter the staff key (STAFF_API_KEY in your .env) in the yellow bar to see and edit desk data."}</p>
    </div>
  );
}
