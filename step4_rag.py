import operator
import time
from typing import Annotated, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from llm import overload_retry, with_backup
from rag import search

MAX_REWRITES = 2


# ---------- 1. State ----------
class RagState(TypedDict):
    question: str
    query: str            # what we actually search for (may be rewritten)
    docs: list[str]
    relevant: bool
    attempts: int
    repeated: bool        # True if a rewrite produced the same query again
    answer: str
    steps: Annotated[list[str], operator.add]


# ---------- 2. Structured outputs ----------
class Grade(BaseModel):
    relevant: bool = Field(description="True only if the sections contain the answer")
    reason: str = Field(description="One short sentence")


class Rewrite(BaseModel):
    query: str = Field(description="A short keyword search query, 2 to 6 words")


grader = with_backup(lambda m: m.with_structured_output(Grade))
rewriter = with_backup(lambda m: m.with_structured_output(Rewrite))
writer = with_backup(lambda m: m)


# ---------- 3. Nodes ----------
def retrieve(state: RagState) -> dict:
    query = state.get("query") or state["question"]
    return {"query": query, "docs": search(query), "steps": [f"retrieve({query!r})"]}


def grade(state: RagState) -> dict:
    if not state["docs"]:
        return {"relevant": False, "steps": ["grade: nothing found"]}
    result = grader.invoke([
        ("system", "Decide if these policy sections answer the passenger's question."),
        ("human", f"Question: {state['question']}\n\nSections:\n\n" + "\n\n".join(state["docs"])),
    ])
    return {"relevant": result.relevant,
            "steps": [f"grade: {result.relevant} ({result.reason})"]}


def rewrite(state: RagState) -> dict:
    result = rewriter.invoke([
        ("system", "Answer the passenger using ONLY the policy sections below. Use only the "
           "section(s) that answer the question; ignore the others. Cite the section "
           "title in square brackets. Two to four sentences."),
        ("human", f"Question: {state['question']}\nPrevious query that failed: {state['query']}"),
    ])
    new_query = result.query.strip()
    repeated = new_query.lower() == state["query"].strip().lower()
    return {"query": new_query,
            "attempts": state["attempts"] + 1,
            "repeated": repeated,
            "steps": [f"rewrite -> {new_query!r}" + ("  (same as before)" if repeated else "")]}


def generate(state: RagState) -> dict:
    response = writer.invoke([
        ("system", "Answer the passenger using ONLY the policy sections below. "
                   "Cite the section title in square brackets. Two to four sentences."),
        ("human", f"Question: {state['question']}\n\nSections:\n\n" + "\n\n".join(state["docs"])),
    ])
    return {"answer": response.text, "steps": ["generate"]}


def give_up(state: RagState) -> dict:
    return {"answer": "I couldn't find this in our transit hotel policy. "
                      "I've passed your question to a staff member.",
            "steps": ["give_up"]}


# ---------- 4. Routers ----------
def after_grade(state: RagState) -> Literal["generate", "rewrite", "give_up"]:
    if state["relevant"]:
        return "generate"
    if state["attempts"] < MAX_REWRITES:
        return "rewrite"
    return "give_up"


def after_rewrite(state: RagState) -> Literal["retrieve", "give_up"]:
    return "give_up" if state["repeated"] else "retrieve"


# ---------- 5. Graph ----------
builder = StateGraph(RagState)
builder.add_node("retrieve", retrieve)
builder.add_node("grade", grade, retry_policy=overload_retry)
builder.add_node("rewrite", rewrite, retry_policy=overload_retry)
builder.add_node("generate", generate, retry_policy=overload_retry)
builder.add_node("give_up", give_up)

builder.add_edge(START, "retrieve")
builder.add_edge("retrieve", "grade")
builder.add_conditional_edges("grade", after_grade)
builder.add_conditional_edges("rewrite", after_rewrite)   # the cycle, with an early exit
builder.add_edge("generate", END)
builder.add_edge("give_up", END)
graph = builder.compile()


# ---------- 6. Try it ----------
if __name__ == "__main__":
    questions = [
        "Do I get a free hotel if my connection is 10 hours?",       # easy: same words
        "I'm stuck between flights overnight, can I get a room?",    # needs a rewrite
        "The bus to my hotel hasn't come, what should I do?",        # 'bus' vs 'shuttle'
        "Can I bring my cat to the hotel?",                          # not in policy -> give_up
    ]
    for q in questions:
        start = time.perf_counter()
        out = graph.invoke({"question": q, "attempts": 0, "repeated": False})
        print(f"\n=== {q}   ({time.perf_counter() - start:.1f}s)")
        for s in out["steps"]:
            print("   ", s)
        print("  ANSWER:", out["answer"])