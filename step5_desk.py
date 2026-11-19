import sqlite3
import sys
import time
import uuid
from typing import Literal, Optional

from langchain_core.messages import AIMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from pydantic import Field

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
def classify(state: DeskState) -> dict:
    instructions = (DESK_SYSTEM + "\nClassify the passenger's LATEST message. "
                    "Use the earlier conversation only as context.")
    result = classifier.invoke([("system", instructions), ("human", transcript(state))])
    return {
        "category": result.category,
        "booking_ref": result.booking_ref or state.get("booking_ref"),  # keep earlier ref
        "urgent": result.urgent,
    }


def status_agent(state: DeskState) -> dict:
    response = llm_with_tools.invoke([AGENT_SYSTEM] + state["messages"])
    return {"messages": [response]}


def policy(state: DeskState) -> dict:
    question = last_user_text(state)
    out = policy_graph.invoke({"question": question, "attempts": 0, "repeated": False})
    return {"messages": [AIMessage(out["answer"])]}


def complaint(state: DeskState) -> dict:
    prefix = "This is marked urgent. " if state.get("urgent") else ""
    text = prefix + "I'm sorry about this. A duty manager will review it within 48 hours."
    return {"messages": [AIMessage(text)]}


def cancel(state: DeskState) -> dict:  # Step 6 adds human approval here
    ref = state.get("booking_ref") or "your booking"
    text = f"I can request cancellation of {ref}. A staff member must approve it."
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

# ---------- 6. Memory: save every step to memory.db, per thread_id ----------
conn = sqlite3.connect("memory.db", check_same_thread=False)
graph = builder.compile(checkpointer=SqliteSaver(conn))


# ---------- 7. A simple chat in the terminal ----------
def show_state(config: dict) -> None:
    values = graph.get_state(config).values
    print(f"  category={values.get('category')}  booking_ref={values.get('booking_ref')}"
          f"  urgent={values.get('urgent')}  messages={len(values.get('messages', []))}")


def chat(thread_id: str) -> None:
    config = {"configurable": {"thread_id": thread_id}}
    print(f"TransitDesk  (thread: {thread_id})   commands: /state  /new  /quit")
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

        start = time.perf_counter()
        out = graph.invoke({"messages": [("human", text)]}, config)
        elapsed = time.perf_counter() - start
        print(f"Desk: {out['messages'][-1].text}")
        print(f"      ({out['category']}, {elapsed:.1f}s)")


if __name__ == "__main__":
    chat(sys.argv[1] if len(sys.argv) > 1 else "demo")