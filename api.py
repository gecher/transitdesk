"""Step 7b: TransitDesk as a web API (FastAPI).

Passenger side:  POST /chat                 -> streams NDJSON events (one JSON object per line)
                 GET  /threads/{thread_id}  -> the saved conversation
Staff side:      GET  /approvals/{thread_id}   (needs header X-Staff-Key)
                 POST /approvals/{thread_id}   -> approve or reject; resumes the paused graph

Run:  uvicorn api:app --reload      then open http://127.0.0.1:8000/docs
"""
import json
import os

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from langgraph.types import Command
from pydantic import BaseModel

from step6_desk import graph, pending_requests   # also loads .env through llm.py

STAFF_KEY = os.getenv("STAFF_API_KEY", "")
TOKEN_NODES = {"status_agent", "generate"}

app = FastAPI(title="TransitDesk API", version="0.7")


class ChatIn(BaseModel):
    thread_id: str
    message: str


class Decision(BaseModel):
    approved: bool
    note: str = ""
    confirm_ref: str = ""     # required when the request carries a warning


def config_for(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def event(**data) -> str:
    return json.dumps(data) + "\n"


def run_stream(graph_input, config: dict):
    """Yield NDJSON events while the graph runs."""
    streamed = False
    try:
        for namespace, mode, chunk in graph.stream(graph_input, config,
                                                   stream_mode=["updates", "messages"],
                                                   subgraphs=True):
            if mode == "updates":
                parent = namespace[0].split(":")[0] + "/" if namespace else ""
                for node in chunk:
                    if node != "__interrupt__":
                        yield event(type="node", node=parent + node)
            else:
                piece, meta = chunk
                if meta.get("langgraph_node") in TOKEN_NODES and piece.text:
                    streamed = True
                    yield event(type="token", text=piece.text)

        pending = pending_requests(config)
        if pending:
            yield event(type="approval_needed", booking_ref=pending[0]["booking_ref"])
        else:
            values = graph.get_state(config).values
            yield event(type="done", category=values.get("category"),
                        reply=values["messages"][-1].text, streamed=streamed)
    except Exception as e:                         # the stream has started: report, don't crash
        yield event(type="error", message=str(e)[:300])


def require_staff(key: str) -> None:
    if not STAFF_KEY or key != STAFF_KEY:
        raise HTTPException(status_code=401, detail="Staff key required")


# ---------------- passenger side ----------------
@app.post("/chat")
def chat(body: ChatIn):
    config = config_for(body.thread_id)
    if pending_requests(config):
        raise HTTPException(status_code=409,
                            detail="A cancellation in this conversation is waiting for staff approval.")
    return StreamingResponse(run_stream({"messages": [("human", body.message)]}, config),
                             media_type="application/x-ndjson")


@app.get("/threads/{thread_id}")
def get_thread(thread_id: str):
    values = graph.get_state(config_for(thread_id)).values
    messages = [{"role": m.type, "text": m.text} for m in values.get("messages", [])
                if m.type in ("human", "ai") and m.text]
    return {"thread_id": thread_id, "booking_ref": values.get("booking_ref"), "messages": messages}


# ---------------- staff side ----------------
@app.get("/approvals/{thread_id}")
def get_approvals(thread_id: str, x_staff_key: str = Header(default="")):
    require_staff(x_staff_key)
    return {"pending": pending_requests(config_for(thread_id))}


@app.post("/approvals/{thread_id}")
def decide(thread_id: str, decision: Decision, x_staff_key: str = Header(default="")):
    require_staff(x_staff_key)
    config = config_for(thread_id)
    pending = pending_requests(config)
    if not pending:
        raise HTTPException(status_code=404, detail="Nothing is waiting for approval in this thread.")

    request = pending[0]
    if decision.approved and request.get("warning"):
        if decision.confirm_ref.strip().upper() != request["booking_ref"]:
            raise HTTPException(status_code=422, detail=(
                f"WARNING: {request['warning']}. To approve anyway, "
                f"send confirm_ref = {request['booking_ref']}."))

    out = graph.invoke(Command(resume={"approved": decision.approved, "note": decision.note}),
                       config)
    return {"reply": out["messages"][-1].text}
