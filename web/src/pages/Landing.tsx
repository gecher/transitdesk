import { useEffect } from "react";
import { Brand, GITHUB_PROFILE, GITHUB_REPO } from "../components/Brand";
import { linkProps } from "../router";

const STEPS = [
  { title: "Understand", text: "An LLM classifies the message into status, cancel, policy, complaint or other, and pulls out urgency. Booking references are read by code, never guessed." },
  { title: "Look it up", text: "For a booking question the agent calls tools on the live database: the booking, then the hotel. Every lookup is shown under the answer." },
  { title: "Check the rules", text: "Policy questions go to a corrective RAG loop: retrieve, grade the result, rewrite the search if it missed, and give up honestly after two tries." },
  { title: "Ask a person", text: "Cancelling changes data, so the graph pauses with interrupt() and waits, for hours if needed, until a staff member approves." },
  { title: "Remember", text: "Every step is checkpointed in Postgres, so a conversation and a waiting approval survive restarts and new servers." },
];

const FOUND = [
  { what: "It asked to cancel the wrong booking", fix: "With two references in a conversation, the LLM picked the old one. Exact IDs are now read by code; the LLM only decides intent." },
  { what: "I approved the wrong request myself", fix: "The approval screen now warns when the message mentions a different booking, and asks you to type the reference to confirm." },
  { what: "A missing key took the whole site down", fix: "The app now starts with whatever providers have keys, and explains in the chat what is missing." },
];

const STACK = ["LangGraph 1.2", "Python · FastAPI", "Groq gpt-oss-120b + Gemini fallback", "Postgres (Neon) checkpointer", "React 19 · TypeScript · Vite", "Vercel"];

export function Landing() {
  useEffect(() => {
    document.title = "TransitDesk: an AI desk agent that checks before it answers";
  }, []);

  return (
    <div className="landing">
      <header className="topbar plain">
        <Brand subtitle="LangGraph agent" />
        <div className="spacer" />
        <a className="topnav-link" href={GITHUB_REPO} target="_blank" rel="noopener noreferrer">Source</a>
        <a className="btn primary" {...linkProps("/console")}>Open the console</a>
      </header>

      <section className="hero">
        <div className="sign" aria-label="Transit hotel desk">
          <div className="sign-row">
            <svg className="sign-arrow" viewBox="0 0 48 48" aria-hidden="true">
              <path d="M8 24h28M26 12l12 12-12 12" fill="none" stroke="currentColor" strokeWidth="5" strokeLinecap="square" />
            </svg>
            <span className="sign-label">Transit hotel desk</span>
            <span className="sign-gate">Agent on duty</span>
          </div>
          <h1>An AI desk agent that checks the booking before it answers.</h1>
          <p className="lede">
            TransitDesk handles hotel requests from airline transit passengers. It reads the real booking, follows
            written policy, asks a person before it cancels anything, and is tested on 21 labelled cases.
          </p>
          <div className="cta-row">
            <a className="btn ink big" {...linkProps("/console")}>Try it in the console</a>
            <a className="btn outline big" href={GITHUB_REPO} target="_blank" rel="noopener noreferrer">Read the code</a>
          </div>
        </div>

        <figure className="transcript" aria-label="Example conversation">
          <figcaption>A real exchange, as the console shows it</figcaption>
          <div className="t-msg you">I want to cancel ET-4471, my uncle is picking me up.</div>
          <div className="t-step"><span>classify</span> cancel · ref ET-4471</div>
          <div className="t-step"><span>lookup</span> get_booking("ET-4471") → Liya Tesfaye, Skylight Hotel, 21 Nov</div>
          <div className="t-step wait"><span>interrupt</span> waiting for staff approval</div>
          <div className="t-approve">
            <b>Staff:</b> Approve cancellation of ET-4471?
            <span className="t-btns"><i className="yes">Approve</i><i>Reject</i></span>
          </div>
          <div className="t-msg desk">Your booking ET-4471 at Skylight Hotel for the night of 2026-11-21 has been cancelled.</div>
        </figure>
      </section>

      <section className="band">
        <h2>How a request moves through the graph</h2>
        <ol className="steps">
          {STEPS.map((s, i) => (
            <li key={s.title}>
              <span className="step-no">{i + 1}</span>
              <h3>{s.title}</h3>
              <p>{s.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="band two-col">
        <div>
          <h2>Measured, not assumed</h2>
          <p className="section-lede">Every change was compared against the version before it, on the same test set.</p>
          <dl className="metrics">
            <div><dt>Routing accuracy</dt><dd><s>1/5</s> 5/5</dd><p>Keyword rules against the LLM classifier, on the first labelled tickets.</p></div>
            <div><dt>Classification time</dt><dd>0.6 s</dd><p>After moving from a high-thinking model to Groq at low reasoning effort.</p></div>
            <div><dt>Evaluation suite</dt><dd>21 cases</dd><p>Route, booking reference, safe actions, required facts, plus an LLM judge for grounding.</p></div>
          </dl>
        </div>
        <div>
          <h2>What testing caught</h2>
          <p className="section-lede">The design came from failures, each fixed and written down.</p>
          <ul className="found">
            {FOUND.map((f) => (
              <li key={f.what}><h3>{f.what}</h3><p>{f.fix}</p></li>
            ))}
          </ul>
        </div>
      </section>

      <section className="band stack-band">
        <h2>Built with</h2>
        <ul className="stack">{STACK.map((s) => <li key={s}>{s}</li>)}</ul>
        <a className="btn primary big" {...linkProps("/console")}>Open the console</a>
      </section>

      <footer className="site-foot">
        <span>All bookings, hotels and policies are fictional.</span>
        <a href={GITHUB_PROFILE} target="_blank" rel="noopener noreferrer">Built by Getacher Ashebir</a>
      </footer>
    </div>
  );
}
