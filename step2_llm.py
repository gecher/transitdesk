import operator
import time
from typing import Annotated, Literal, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy
from pydantic import BaseModel, Field

from llm import overload_retry, with_backup
from step1_graph import classify as keyword_classify   # old version, for comparison

Category = Literal["status", "cancel", "policy", "complaint"]


# ---------- 1. The shape we force the LLM to answer in ----------
class Classification(BaseModel):
    """How to handle a message sent to the transit-hotel desk."""
    category: Category = Field(description="The type of request")
    booking_ref: Optional[str] = Field(
        default=None, description="Booking reference such as ET-4471, only if given")
    urgent: bool = Field(
        description="True if the passenger is at the airport now or the issue is within 6 hours")
    reason: str = Field(description="One short sentence explaining the category")


# ---------- 2. Graph state ----------
class TicketState(TypedDict):
    ticket: str
    category: str
    booking_ref: Optional[str]
    urgent: bool
    reason: str
    reply: str
    steps: Annotated[list[str], operator.add]


SYSTEM = """You classify messages sent to an airline's hotel desk for transit passengers.
Categories:
- status: asks about an existing hotel booking (confirmed? which hotel? pickup time?)
- cancel: wants to cancel or change an existing booking
- policy: asks about rules (who gets a free hotel, meals, visas, transport)
- complaint: unhappy with a stay, staff, transport or service"""

classifier = with_backup(lambda m: m.with_structured_output(Classification))


# ---------- 3. Nodes ----------
def classify(state: TicketState) -> dict:
    result = classifier.invoke([("system", SYSTEM), ("human", state["ticket"])])
    return {
        "category": result.category,
        "booking_ref": result.booking_ref,
        "urgent": result.urgent,
        "reason": result.reason,
        "steps": ["classify"],
    }


def handle_status(state: TicketState) -> dict:
    if not state.get("booking_ref"):
        reply = "Could you share your booking reference (for example ET-1234)?"
    else:
        reply = f"Checking booking {state['booking_ref']} for you."
    return {"reply": reply, "steps": ["status"]}


def handle_cancel(state: TicketState) -> dict:
    return {"reply": "A cancellation needs approval from a staff member.", "steps": ["cancel"]}


def handle_policy(state: TicketState) -> dict:
    return {"reply": "Here is our hotel policy for transit passengers.", "steps": ["policy"]}


def handle_complaint(state: TicketState) -> dict:
    prefix = "URGENT: " if state.get("urgent") else ""
    return {"reply": prefix + "I'm sorry. I've passed this to our duty manager.",
            "steps": ["complaint"]}


def route(state: TicketState) -> Category:
    return state["category"]


# ---------- 4. Retry only temporary errors (overload / rate limit) ----------
def is_temporary(error: Exception) -> bool:
    text = str(error)
    return any(code in text for code in ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED"))


overload_retry = RetryPolicy(max_attempts=4, initial_interval=2.0, backoff_factor=2.0,
                             retry_on=is_temporary)


# ---------- 5. Build the graph ----------
builder = StateGraph(TicketState)
builder.add_node("classify", classify, retry_policy=overload_retry)
builder.add_node("status", handle_status)
builder.add_node("cancel", handle_cancel)
builder.add_node("policy", handle_policy)
builder.add_node("complaint", handle_complaint)
builder.add_edge(START, "classify")
builder.add_conditional_edges("classify", route)
for node in ("status", "cancel", "policy", "complaint"):
    builder.add_edge(node, END)
graph = builder.compile()


# ---------- 6. Evaluate: keyword baseline vs LLM ----------
if __name__ == "__main__":
    tests = [  # (ticket, correct category)
        ("Is my room at the Skylight confirmed? Ref ET-5520", "status"),
        ("I don't need the room anymore, my uncle will pick me up. ET-3301", "cancel"),
        ("The shuttle never came and I waited two hours at the airport!", "complaint"),
        ("Can I get a free hotel if my connection is 7 hours?", "policy"),
        ("I'm at the transfer desk now and nobody can find my reservation", "status"),
    ]
    kw_correct = llm_correct = 0
    times = []
    for ticket, expected in tests:
        kw = keyword_classify({"ticket": ticket})["category"]
        start = time.perf_counter()
        out = graph.invoke({"ticket": ticket})
        times.append(time.perf_counter() - start)
        kw_correct += kw == expected
        llm_correct += out["category"] == expected
        print(f"\n{ticket}")
        print(f"  expected: {expected:<9} keyword: {kw:<9} llm: {out['category']}"
              f"   ({times[-1]:.1f}s)")
        print(f"  ref: {out['booking_ref']}  urgent: {out['urgent']}  why: {out['reason']}")
        print(f"  reply: {out['reply']}")

    n = len(tests)
    print(f"\nAccuracy  keyword: {kw_correct}/{n}   llm: {llm_correct}/{n}")
    print(f"LLM time  average: {sum(times) / n:.1f}s   slowest: {max(times):.1f}s")