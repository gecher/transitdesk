import operator
from typing import Annotated, Literal, TypedDict

from langgraph.graph import END, START, StateGraph


class TicketState(TypedDict):
    ticket: str                                # input: the passenger's message
    category: str                              # written by classify
    reply: str                                 # written by a handler
    steps: Annotated[list[str], operator.add]  # reducer: nodes APPEND to this list


def classify(state: TicketState) -> dict:
    text = state["ticket"].lower()
    if "cancel" in text:
        category = "cancel"
    elif "status" in text or "booking" in text:
        category = "status"
    else:
        category = "policy"
    return {"category": category, "steps": ["classify"]}   # only the changed keys


def handle_status(state: TicketState) -> dict:
    return {"reply": "Let me check your booking status.", "steps": ["status"]}


def handle_cancel(state: TicketState) -> dict:
    return {"reply": "A cancellation needs approval from a staff member.", "steps": ["cancel"]}


def handle_policy(state: TicketState) -> dict:
    return {"reply": "Here is our hotel policy for transit passengers.", "steps": ["policy"]}


def route(state: TicketState) -> Literal["status", "cancel", "policy"]:
    return state["category"]          # the return value = name of the next node


builder = StateGraph(TicketState)
builder.add_node("classify", classify)
builder.add_node("status", handle_status)
builder.add_node("cancel", handle_cancel)
builder.add_node("policy", handle_policy)

builder.add_edge(START, "classify")
builder.add_conditional_edges("classify", route)
for node in ("status", "cancel", "policy"):
    builder.add_edge(node, END)

graph = builder.compile()

if __name__ == "__main__":
    print(graph.get_graph().draw_mermaid())   # diagram text: paste into mermaid.live

    tickets = [
        "What is the status of my booking ET-4471?",
        "Please cancel my hotel, my flight changed.",
        "Do I get a free hotel for a 9-hour layover?",
    ]
    for t in tickets:
        result = graph.invoke({"ticket": t})
        print(f"\n{t}\n  category: {result['category']}\n  path:     {result['steps']}"
              f"\n  reply:    {result['reply']}")