import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { ApiError, getThread, newThreadId, streamChat } from "../api";
import type { ChatMessage, Lookup } from "../types";

interface Props {
  threadId: string;
  onThreadChange: (id: string) => void;
  reloadVersion: number;                       // bumped when a staff decision adds a reply
  onActiveRef: (ref: string | null) => void;   // highlight the booking being discussed
  onAfterReply: () => void;                    // refresh the tables
  onApprovalNeeded: () => void;                // refresh the approvals inbox
}

const EXAMPLES = [
  "Is ET-1377 confirmed?",
  "How do I get to my hotel? ET-1204",
  "Can I get a free hotel for a 10-hour connection?",
  "Please cancel ET-2156",
];

let nextId = 1;

function pretty(text: string): string {
  try {
    return JSON.stringify(JSON.parse(text), null, 1);
  } catch {
    return text;
  }
}

function LookupList({ lookups }: { lookups: Lookup[] }) {
  return (
    <details className="lookups">
      <summary>What the agent looked up ({lookups.length})</summary>
      {lookups.map((l, i) => (
        <div className="lookup" key={i}>
          <code>
            {l.name}({Object.values(l.args).map((v) => JSON.stringify(v)).join(", ")})
          </code>
          {l.result !== undefined && <pre>{pretty(l.result)}</pre>}
        </div>
      ))}
    </details>
  );
}

export function Chat({ threadId, onThreadChange, reloadVersion, onActiveRef, onAfterReply, onApprovalNeeded }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [threadDraft, setThreadDraft] = useState(threadId);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => setThreadDraft(threadId), [threadId]);

  // Load the saved conversation when the thread changes, or after a staff decision.
  useEffect(() => {
    let cancelled = false;
    getThread(threadId)
      .then((t) => {
        if (cancelled) return;
        const loaded: ChatMessage[] = t.messages.map((m) => ({
          id: nextId++,
          role: m.role === "human" ? "you" : "desk",
          text: m.text,
        }));
        if (t.waiting_for_approval) {
          loaded.push({ id: nextId++, role: "note", text: "A cancellation in this conversation is waiting for staff approval." });
        }
        setMessages(loaded);
        onActiveRef(t.booking_ref);
      })
      .catch(() => !cancelled && setMessages([]));
    return () => {
      cancelled = true;
    };
  }, [threadId, reloadVersion, onActiveRef]);

  useEffect(() => {
    const box = listRef.current;
    if (box) box.scrollTop = box.scrollHeight;
  }, [messages]);

  async function send(text: string) {
    const deskId = nextId++;
    const draft: ChatMessage = { id: deskId, role: "desk", text: "…", lookups: [] };
    const lookups = draft.lookups!;
    setMessages((ms) => [...ms, { id: nextId++, role: "you", text }, { ...draft }]);
    const update = () => {
      const copy: ChatMessage = { ...draft, lookups: lookups.map((l) => ({ ...l })) };
      setMessages((ms) => ms.map((m) => (m.id === deskId ? copy : m)));
    };

    const nodes: string[] = [];
    let gotText = false;
    let category = "";
    const started = performance.now();
    let firstToken = 0;
    setBusy(true);
    try {
      await streamChat(threadId, text, (e) => {
        switch (e.type) {
          case "node":
            nodes.push(e.node);
            break;
          case "token":
            if (!gotText) {
              draft.text = "";
              gotText = true;
              firstToken = performance.now();
            }
            draft.text += e.text;
            update();
            break;
          case "tool_call":
            lookups.push({ name: e.name, args: e.args });
            update();
            break;
          case "tool_result": {
            const last = lookups[lookups.length - 1];
            if (last && last.result === undefined) last.result = e.content;
            else lookups.push({ name: e.name, args: {}, result: e.content });
            const ref = e.content.match(/"ref":\s*"(ET-\d+)"/)?.[1];
            if (ref) onActiveRef(ref);
            update();
            break;
          }
          case "approval_needed":
            draft.role = "note";
            draft.text = `Your request for ${e.booking_ref} is waiting for staff approval.`;
            gotText = true;
            onActiveRef(e.booking_ref);
            onApprovalNeeded();
            update();
            break;
          case "done":
            if (!gotText) draft.text = e.reply;
            category = e.category;
            if (e.booking_ref) onActiveRef(e.booking_ref);
            update();
            break;
          case "error":
            draft.role = "note";
            draft.text = "Error: " + e.message;
            gotText = true;
            update();
            break;
        }
      });
      const total = ((performance.now() - started) / 1000).toFixed(1);
      const first = firstToken ? ` · first word ${((firstToken - started) / 1000).toFixed(1)}s` : "";
      draft.meta = `${category ? category + " · " : ""}path: ${nodes.join(" → ")} · ${total}s${first}`;
      update();
    } catch (err) {
      draft.role = "note";
      draft.text = err instanceof ApiError ? err.message : "Could not reach the server.";
      update();
    } finally {
      setBusy(false);
      onAfterReply();
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    void send(text);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      e.currentTarget.form?.requestSubmit();
    }
  }

  function commitThread() {
    const id = threadDraft.trim();
    if (id && id !== threadId) onThreadChange(id);
    else setThreadDraft(threadId);
  }

  return (
    <section className="panel chat" aria-label="Passenger chat">
      <div className="panel-head">
        <h2>Passenger chat</h2>
        <div className="spacer" />
        <div className="thread-box">
          <label htmlFor="threadId">Thread</label>
          <input
            id="threadId"
            value={threadDraft}
            onChange={(e) => setThreadDraft(e.target.value)}
            onBlur={commitThread}
            onKeyDown={(e) => e.key === "Enter" && commitThread()}
          />
          <button type="button" className="btn ghost small" id="newThread" title="Start a new conversation"
                  onClick={() => onThreadChange(newThreadId())}>
            New
          </button>
        </div>
      </div>

      <div id="messages" ref={listRef}>
        {messages.length === 0 ? (
          <div className="empty-chat">
            <p>Chat as a passenger. Every booking lookup the agent makes appears under its answer, so you can compare it with the table.</p>
            {EXAMPLES.map((x) => (
              <button key={x} type="button" className="chip" onClick={() => setInput(x)}>
                {x}
              </button>
            ))}
          </div>
        ) : (
          messages.map((m) => (
            <div key={m.id} className={`msg ${m.role}`}>
              {m.text}
              {m.lookups && m.lookups.length > 0 && <LookupList lookups={m.lookups} />}
              {m.meta && <div className="meta">{m.meta}</div>}
            </div>
          ))
        )}
      </div>

      <form className="composer" id="composer" onSubmit={submit}>
        <textarea
          id="input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Write as a passenger, e.g. Is ET-1377 confirmed?"
          aria-label="Message"
        />
        <button className="btn" id="send" disabled={busy || !input.trim()}>
          Send
        </button>
      </form>
    </section>
  );
}
