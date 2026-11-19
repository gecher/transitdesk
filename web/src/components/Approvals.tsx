import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { Notify } from "../hooks";
import type { Approval } from "../types";
import { Locked } from "./common";

interface Props {
  staffKey: string;
  version: number;                         // bumped when the chat creates a request
  notify: Notify;
  onCount: (n: number) => void;            // for the badge on the tab
  onDecided: (threadId: string) => void;   // so the chat and tables can refresh
}

function ApprovalCard({ request, staffKey, notify, onDone }: {
  request: Approval;
  staffKey: string;
  notify: Notify;
  onDone: () => void;
}) {
  const [note, setNote] = useState("");
  const [confirmRef, setConfirmRef] = useState("");
  const [busy, setBusy] = useState(false);

  async function decide(approved: boolean) {
    setBusy(true);
    try {
      await api(`/approvals/${encodeURIComponent(request.thread_id)}`, staffKey, {
        method: "POST",
        body: JSON.stringify({ approved, note: note.trim(), confirm_ref: confirmRef }),
      });
      notify(approved ? `${request.booking_ref} cancelled` : "Request rejected");
      onDone();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Could not save the decision", true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={"card" + (request.warning ? " warn" : "")}>
      <h3>Cancel {request.booking_ref}</h3>
      {request.warning && <div className="warning">Check this: {request.warning}</div>}
      <dl>
        <dt>Passenger</dt><dd>{request.passenger}</dd>
        <dt>Hotel, night</dt><dd>{request.hotel}, {request.night}</dd>
        <dt>Passenger wrote</dt><dd>“{request.passenger_message}”</dd>
        <dt>Conversation</dt><dd>{request.thread_id}</dd>
      </dl>
      <div className="row">
        {request.warning && (
          <input value={confirmRef} onChange={(e) => setConfirmRef(e.target.value)}
                 placeholder={`Type ${request.booking_ref} to approve`} size={22} aria-label="Confirm reference" />
        )}
        <button type="button" className="btn ok" disabled={busy} onClick={() => decide(true)}>Approve cancellation</button>
        <input value={note} onChange={(e) => setNote(e.target.value)}
               placeholder="Note for the passenger (if rejecting)" size={34} aria-label="Note for the passenger" />
        <button type="button" className="btn danger" disabled={busy} onClick={() => decide(false)}>Reject</button>
      </div>
    </div>
  );
}

export function Approvals({ staffKey, version, notify, onCount, onDecided }: Props) {
  const [items, setItems] = useState<Approval[]>([]);

  const load = useCallback(async () => {
    if (!staffKey) {
      setItems([]);
      onCount(0);
      return;
    }
    try {
      const r = await api<{ pending: Approval[] }>("/approvals", staffKey);
      setItems(r.pending);
      onCount(r.pending.length);
    } catch {
      /* a failed poll is not worth a message; the next one retries */
    }
  }, [staffKey, onCount]);

  useEffect(() => {                         // load now, then check every 5 seconds
    void load();
    if (!staffKey) return;
    const t = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(t);
  }, [load, version, staffKey]);

  if (!staffKey) {
    return <Locked text="Approving cancellations needs the staff key. Without it, cancellation requests wait here for a staff member." />;
  }
  return (
    <>
      <p className="hint">Cancellations wait here until a staff member decides. Evaluation runs are not shown.</p>
      {items.length === 0 ? (
        <p className="hint">Nothing is waiting for approval.</p>
      ) : (
        items.map((r) => (
          <ApprovalCard key={r.thread_id + r.booking_ref} request={r} staffKey={staffKey} notify={notify}
                        onDone={() => { void load(); onDecided(r.thread_id); }} />
        ))
      )}
    </>
  );
}
