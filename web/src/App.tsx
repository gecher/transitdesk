import { useCallback, useEffect, useState } from "react";
import { getConfig, newThreadId } from "./api";
import { Approvals } from "./components/Approvals";
import { Bookings } from "./components/Bookings";
import { Chat } from "./components/Chat";
import { Hotels } from "./components/Hotels";
import { useStoredState, useToast } from "./hooks";

type Tab = "bookings" | "hotels" | "approvals";
const TABS: { id: Tab; label: string }[] = [
  { id: "bookings", label: "Bookings" },
  { id: "hotels", label: "Hotels" },
  { id: "approvals", label: "Approvals" },
];

export default function App() {
  const [staffKey, setStaffKey] = useStoredState("staffKey", () => "");
  const [keyDraft, setKeyDraft] = useState(staffKey);
  const [threadId, setThreadId] = useStoredState("thread", newThreadId);
  const [publicRead, setPublicRead] = useState(false);
  const [tab, setTab] = useState<Tab>("bookings");
  const [activeRef, setActiveRef] = useState<string | null>(null);
  const [approvalCount, setApprovalCount] = useState(0);
  // "versions": bump a number to tell a part of the page to reload its data
  const [dataVersion, setDataVersion] = useState(0);
  const [approvalVersion, setApprovalVersion] = useState(0);
  const [threadVersion, setThreadVersion] = useState(0);
  const { toast, notify } = useToast();

  useEffect(() => {
    getConfig().then((c) => setPublicRead(c.public_read)).catch(() => undefined);
  }, []);

  const dataChanged = useCallback(() => setDataVersion((v) => v + 1), []);
  const approvalRequested = useCallback(() => setApprovalVersion((v) => v + 1), []);
  const decided = useCallback(
    (decidedThread: string) => {
      if (decidedThread === threadId) setThreadVersion((v) => v + 1);   // show the reply in the chat
      setDataVersion((v) => v + 1);
    },
    [threadId],
  );

  const commitKey = () => setStaffKey(keyDraft.trim());
  const canRead = !!staffKey || publicRead;

  return (
    <>
      <header>
        <div className="brand">
          <svg width="34" height="34" viewBox="0 0 34 34" aria-hidden="true">
            <rect x="1" y="1" width="32" height="32" rx="5" fill="#10233f" />
            <path d="M8 23h18M10 23V13l7-4 7 4v10M14 23v-5h6v5" fill="none" stroke="#f5c518" strokeWidth="2.4" strokeLinejoin="round" />
          </svg>
          <div>
            <h1>TransitDesk</h1>
            <span>Transit hotel desk · agent console</span>
          </div>
        </div>
        <div className="spacer" />
        <label htmlFor="staffKey">Staff key</label>
        <input
          id="staffKey"
          type="password"
          value={keyDraft}
          onChange={(e) => setKeyDraft(e.target.value)}
          onBlur={commitKey}
          onKeyDown={(e) => e.key === "Enter" && commitKey()}
          placeholder="STAFF_API_KEY from .env"
          autoComplete="off"
        />
        <a className="credit" href="https://github.com/gecher" target="_blank" rel="noopener noreferrer">
          Built by Getacher Ashebir
        </a>
      </header>

      <main>
        <Chat
          threadId={threadId}
          onThreadChange={setThreadId}
          reloadVersion={threadVersion}
          onActiveRef={setActiveRef}
          onAfterReply={dataChanged}
          onApprovalNeeded={approvalRequested}
        />

        <section className="panel" aria-label="Desk data">
          <div className="tabs" role="tablist">
            {TABS.map((t) => (
              <button key={t.id} type="button" role="tab" className="tab" data-view={t.id}
                      aria-selected={tab === t.id} onClick={() => setTab(t.id)}>
                {t.label}
                {t.id === "approvals" && approvalCount > 0 && <span className="badge" id="approvalCount">{approvalCount}</span>}
              </button>
            ))}
          </div>
          {/* All views stay mounted so the approvals badge keeps updating. */}
          <div className="view" id="view-bookings" hidden={tab !== "bookings"}>
            <Bookings staffKey={staffKey} canRead={canRead} activeRef={activeRef} version={dataVersion}
                      notify={notify} onChanged={dataChanged} />
          </div>
          <div className="view" id="view-hotels" hidden={tab !== "hotels"}>
            <Hotels staffKey={staffKey} canRead={canRead} version={dataVersion} notify={notify} onChanged={dataChanged} />
          </div>
          <div className="view" id="view-approvals" hidden={tab !== "approvals"}>
            <Approvals staffKey={staffKey} version={approvalVersion} notify={notify}
                       onCount={setApprovalCount} onDecided={decided} />
          </div>
        </section>
      </main>

      <div id="toast" role="status" aria-live="polite" className={(toast.visible ? "show" : "") + (toast.bad ? " bad" : "")}>
        {toast.text}
      </div>
    </>
  );
}
