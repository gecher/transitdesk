import { useEffect, useState } from "react";
import type { Status } from "../types";

export function StatusPill({ status }: { status: Status }) {
  return <span className={`status ${status}`}>{status.charAt(0) + status.slice(1).toLowerCase()}</span>;
}

/** A button that needs two clicks: the first arms it, the second runs the action. */
export function ConfirmButton(props: {
  label: string;
  confirmLabel: string;
  onConfirm: () => void;
  className?: string;
  armedClassName?: string;
}) {
  const { label, confirmLabel, onConfirm, className = "btn small ghost", armedClassName = "btn small danger" } = props;
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    if (!armed) return;
    const t = window.setTimeout(() => setArmed(false), 3000);
    return () => window.clearTimeout(t);
  }, [armed]);
  return (
    <button
      type="button"
      className={armed ? armedClassName : className}
      onClick={() => {
        if (armed) {
          setArmed(false);
          onConfirm();
        } else setArmed(true);
      }}
    >
      {armed ? confirmLabel : label}
    </button>
  );
}

export function Locked({ text }: { text?: string }) {
  return (
    <div className="locked">
      <p>{text ?? "Enter the staff key (STAFF_API_KEY in your .env) in the yellow bar to see and edit desk data."}</p>
    </div>
  );
}
