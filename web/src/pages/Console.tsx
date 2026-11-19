import { useCallback, useEffect, useState } from "react";
import { getConfig, newThreadId } from "../api";
import { Approvals } from "../components/Approvals";
import { Bookings } from "../components/Bookings";
import { Brand, GITHUB_PROFILE } from "../components/Brand";
import { Chat } from "../components/Chat";
import { Hotels } from "../components/Hotels";
import { useStoredState, useToast } from "../hooks";
import { linkProps } from "../router";

type Tab = "bookings" | "hotels" | "approvals";
const TABS: { id: Tab; label: string }[] = [
  { id: "bookings", label: "Bookings" },
  { id: "hotels", label: "Hotels" },
  { id: "approvals", label: "Approvals" },
];

export function Console() {
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
    document.title = "TransitDesk console";
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

  const commitKey = () => {
    const key = keyDraft.trim();
    setStaffKey(key);
    if (key && key !== staffKey) notify("Staff key saved in this browser");
  };
  const canRead = !!staffKey || publicRead;

  return (
    <div className="console">
      <header className="topbar">
        <Brand subtitle="Agent console" />
        <nav className="topnav">
          <a {...linkProps("/")}>Overview</a>
        </nav>
        <div className="spacer" />
        <div className={"keybox" + (staffKey ? " unlocked" : "")}>
          <label htmlFor="staffKey">{staffKey ? "Staff mode" : "Staff key"}</label>
          <input
            id="staffKey"
            type="password"
            value={keyDraft}
            onChange={(e) => setKeyDraft(e.target.value)}
            onBlur={commitKey}
            onKeyDown={(e) => e.key === "Enter" && commitKey()}
            placeholder="Enter to edit data"
            autoComplete="off"
          />
        </div>
        <a className="credit" href={GITHUB_PROFILE} target="_blank" rel="noopener noreferrer">Built by Getacher Ashebir</a>
      </header>

      <main className="workspace">
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
    </div>
  );
}
