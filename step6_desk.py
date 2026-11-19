import re
import sqlite3
import sys
import time
import uuid
from typing import Literal, Optional

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import Command, interrupt
from pydantic import Field

from db import DATA_DIR, USE_POSTGRES, execute, pool, query
from llm import overload_retry, with_backup
from step2_llm import Classification
from step3_agent import SYSTEM as AGENT_SYSTEM, llm_with_tools
from step4_rag import graph as policy_graph
from tools import TOOLS


# ---------- 1. State: messages (with add_messages reducer) + our own fields ----------
class DeskState(MessagesState):
    category: str
    booking_ref: Optional[str]
    urgent: bool


# ---------- 2. Classifier with a fallback category ----------
DeskCategory = Literal["status", "cancel", "policy", "complaint", "other"]


class DeskClassification(Classification):
    category: DeskCategory = Field(description="The type of request")


DESK_SYSTEM = """You classify messages sent to an airline's hotel desk for transit passengers.
Decide by WHOSE question it is, not only by topic.
Categories:
- status: about THIS passenger's own booking or hotel: is it confirmed, which hotel,
  pickup time, how to get to their hotel, their shuttle, the hotel's phone number.
  If a booking was already discussed and the passenger asks about their stay, use status.
- cancel: wants to cancel or change their booking
- policy: general rules that apply to everyone: who gets a free hotel, meals, visas,
  what to do if any shuttle is late. No specific booking is involved.
- complaint: unhappy with a stay, staff, transport or service
- other: greetings, thanks, small talk, or anything not about transit hotels"""

classifier = with_backup(lambda m: m.with_structured_output(DeskClassification))


# ---------- 3. Helpers ----------
def last_user_text(state: DeskState) -> str:
    for m in reversed(state["messages"]):
        if m.type == "human":
            return m.text
    return ""


def transcript(state: DeskState, n: int = 6) -> str:
    """The last few turns as plain text, so the classifier sees context."""
    lines = []
    for m in state["messages"][-n:]:
        if m.type in ("human", "ai") and m.text:
            speaker = "Passenger" if m.type == "human" else "Desk"
            lines.append(f"{speaker}: {m.text}")
    return "\n".join(lines)


# ---------- 4. Nodes ----------
REF_PATTERN = re.compile(r"\bET-?(\d{3,6})\b", re.IGNORECASE)


def refs_in(text: str) -> list[str]:
    """Booking references written in a text, normalised: 'et4471' -> 'ET-4471'."""
    return [f"ET-{digits}" for digits in REF_PATTERN.findall(text)]


def classify(state: DeskState) -> dict:
    instructions = (DESK_SYSTEM + "\nClassify the passenger's LATEST message. "
                    "Use the earlier conversation only as context.")
    result = classifier.invoke([("system", instructions), ("human", transcript(state))])

    # Exact facts come from code, not the LLM: a reference in the LATEST message always wins.
    # (Bug found in testing: with several refs in the conversation, the LLM picked an old one.)
    latest_refs = refs_in(last_user_text(state))
    if latest_refs:
        ref = latest_refs[-1]
    else:
        ref = result.booking_ref or state.get("booking_ref")   # "cancel it" -> use context
    return {"category": result.category, "booking_ref": ref, "urgent": result.urgent}


def status_agent(state: DeskState) -> dict:
    response = llm_with_tools.invoke([AGENT_SYSTEM] + state["messages"])
    return {"messages": [response]}


def policy(state: DeskState, config: RunnableConfig) -> dict:
    question = last_user_text(state)
    # Passing config makes the inner graph part of this run, so its tokens can be streamed.
    out = policy_graph.invoke({"question": question, "attempts": 0, "repeated": False}, config)
    return {"messages": [AIMessage(out["answer"])]}


def complaint(state: DeskState) -> dict:
    prefix = "This is marked urgent. " if state.get("urgent") else ""
    text = prefix + "I'm sorry about this. A duty manager will review it within 48 hours."
    return {"messages": [AIMessage(text)]}


def cancel(state: DeskState) -> dict:
    """Cancel a booking, but only after a staff member approves.

    IMPORTANT: after approval, LangGraph runs this node again FROM THE START.
    So everything before interrupt() must be safe to repeat (reads only),
    and the real change (the UPDATE) must come after interrupt().
    """
    ref = state.get("booking_ref")
    if not ref:
        return {"messages": [AIMessage("Which booking would you like to cancel? "
                                       "Please send the reference, for example ET-1234.")]}

    rows = query("SELECT * FROM bookings WHERE ref = ?", (ref.strip().upper(),))   # read only
    if not rows:
        return {"messages": [AIMessage(f"I couldn't find booking {ref}. "
                                       "Please check the reference.")]}
    booking = rows[0]
    if booking["status"] == "CANCELLED":
        return {"messages": [AIMessage(f"Booking {booking['ref']} is already cancelled.")]}

    # Safety check for the human: does the passenger's message mention a DIFFERENT booking?
    message = last_user_text(state)
    mentioned = refs_in(message)
    warning = ""
    if mentioned and booking["ref"] not in mentioned:
        warning = (f"Message mentions {', '.join(mentioned)}, "
                   f"but this request is for {booking['ref']}")

    # ---- PAUSE: the graph stops here and is saved in memory.db ----
    decision = interrupt({
        "action": "cancel_booking",
        "booking_ref": booking["ref"],
        "passenger": booking["passenger"],
        "hotel": booking["hotel"],
        "night": booking["night"],
        "passenger_message": message,
        "warning": warning,
    })
    # ---- RESUMED: decision is whatever the staff member sent with Command(resume=...) ----

    if decision.get("approved"):
        execute("UPDATE bookings SET status = 'CANCELLED' WHERE ref = ?", (booking["ref"],))
        text = (f"Your booking {booking['ref']} at {booking['hotel']} for the night of "
                f"{booking['night']} has been cancelled.")
    else:
        note = decision.get("note") or "Please contact the transfer desk."
        text = f"A staff member could not approve the cancellation of {booking['ref']}. {note}"
    return {"messages": [AIMessage(text)]}


def other(state: DeskState) -> dict:
    text = ("Hello! I'm the transit hotel desk. I can check your booking, explain hotel "
            "policy, cancel a booking, or take a complaint. How can I help?")
    return {"messages": [AIMessage(text)]}


NEXT_NODE = {
    "status": "status_agent",
    "policy": "policy",
    "complaint": "complaint",
    "cancel": "cancel",
    "other": "other",
}


def route(state: DeskState) -> Literal["status_agent", "policy", "complaint", "cancel", "other"]:
    return NEXT_NODE[state["category"]]


# ---------- 5. Graph ----------
builder = StateGraph(DeskState)
builder.add_node("classify", classify, retry_policy=overload_retry)
builder.add_node("status_agent", status_agent, retry_policy=overload_retry)
builder.add_node("tools", ToolNode(TOOLS))
builder.add_node("policy", policy)
builder.add_node("complaint", complaint)
builder.add_node("cancel", cancel)
builder.add_node("other", other)

builder.add_edge(START, "classify")
builder.add_conditional_edges("classify", route)
builder.add_conditional_edges("status_agent", tools_condition)  # -> "tools" or END
builder.add_edge("tools", "status_agent")                        # the agent loop
for node in ("policy", "complaint", "cancel", "other"):
    builder.add_edge(node, END)

# ---------- 6. Memory: save every step (interrupt() needs this) ----------
# Local: memory.db (SQLite). On Vercel: Postgres, because the server's disk is not kept.
if USE_POSTGRES:
    from langgraph.checkpoint.postgres import PostgresSaver
    checkpointer = PostgresSaver(pool())
    checkpointer.setup()                 # creates the checkpoint tables once; safe to repeat
else:
    conn = sqlite3.connect(DATA_DIR / "memory.db", check_same_thread=False)
    checkpointer = SqliteSaver(conn)
graph = builder.compile(checkpointer=checkpointer)


# ---------- 7. Human in the loop: the staff side ----------
def pending_requests(config: dict) -> list[dict]:
    """Approval requests waiting in this thread (saved in memory.db)."""
    snapshot = graph.get_state(config)
    return [i.value for task in snapshot.tasks for i in task.interrupts]


def staff_review(config: dict) -> None:
    """Simulates a staff member. In a real system this would be a web page or Slack message."""
    for request in pending_requests(config):
        warning = request.get("warning")
        print("\n  +------------- STAFF APPROVAL NEEDED -------------")
        for key, value in request.items():
            if key != "warning":
                print(f"  | {key:<18} {value}")
        if warning:
            print(f"  | !!! WARNING: {warning}")
        print("  +-------------------------------------------------")
        answer = input("  STAFF  approve? [y]es / [n]o / [l]ater: ").strip().lower()
        if answer.startswith("l"):
            print("  (left pending: it is saved, you can /quit and approve after restarting)")
            return
        approved = answer.startswith("y")
        if approved and warning:
            # Stop reflex approvals: with a warning, staff must type the reference itself.
            typed = input(f"  STAFF  type {request['booking_ref']} to confirm: ").strip().upper()
            approved = typed == request["booking_ref"]
            if not approved:
                print("  (reference not confirmed: treated as NOT approved)")
        decision = {"approved": approved, "note": ""}
        if not decision["approved"]:
            decision["note"] = input("  STAFF  note for the passenger: ").strip()
        out = graph.invoke(Command(resume=decision), config)      # continue the paused graph
        print(f"Desk: {out['messages'][-1].text}")


# ---------- 8. A simple chat in the terminal ----------
def show_state(config: dict) -> None:
    snapshot = graph.get_state(config)
    values = snapshot.values
    print(f"  category={values.get('category')}  booking_ref={values.get('booking_ref')}"
          f"  urgent={values.get('urgent')}  messages={len(values.get('messages', []))}")
    print(f"  next={snapshot.next}  pending approvals={len(pending_requests(config))}")


def chat(thread_id: str) -> None:
    config = {"configurable": {"thread_id": thread_id}}
    print(f"TransitDesk  (thread: {thread_id})   commands: /state  /new  /quit")
    staff_review(config)                       # anything left pending from last time?
    while True:
        text = input("\nYou: ").strip()
        if not text:
            continue
        if text == "/quit":
            break
        if text == "/new":
            thread_id = uuid.uuid4().hex[:8]
            config = {"configurable": {"thread_id": thread_id}}
            print(f"(new conversation: {thread_id})")
            continue
        if text == "/state":
            show_state(config)
            continue
        if pending_requests(config):
            print("Desk: Your cancellation is still waiting for staff approval.")
            staff_review(config)
            continue

        start = time.perf_counter()
        out = graph.invoke({"messages": [("human", text)]}, config)
        elapsed = time.perf_counter() - start
        if "__interrupt__" in out:             # the graph paused for approval
            print("Desk: I've sent your cancellation request to a staff member for approval.")
            print(f"      ({out['category']}, {elapsed:.1f}s, waiting for approval)")
            staff_review(config)
        else:
            print(f"Desk: {out['messages'][-1].text}")
            print(f"      ({out['category']}, {elapsed:.1f}s)")


if __name__ == "__main__":
    chat(sys.argv[1] if len(sys.argv) > 1 else "demo")
