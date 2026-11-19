"""TransitDesk web API and console (FastAPI).

Passenger:  POST /chat                    streams NDJSON events
            GET  /threads/{thread_id}     the saved conversation
Staff (header X-Staff-Key):
            GET  /approvals               everything waiting for approval (all conversations)
            POST /approvals/{thread_id}   approve or reject; resumes the paused graph
            GET/POST/PUT/DELETE /api/bookings[/{ref}]
            GET/POST/PUT/DELETE /api/hotels[/{name}]
Console:    GET  /                        the web page in public/index.html

Run locally:  uvicorn api:app --reload      then open http://127.0.0.1:8000
On Vercel:    app.py imports this app; set DATABASE_URL (Neon) so data and memory persist.
"""
import hashlib
import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langgraph.types import Command
from pydantic import BaseModel, Field, field_validator

import db
from llm import available_providers
from step6_desk import graph, pending_requests   # also loads .env through llm.py

STAFF_KEY = os.getenv("STAFF_API_KEY", "")
PUBLIC_READ = os.getenv("PUBLIC_READ", "false").lower() == "true"   # visitors may VIEW demo data
CHAT_PER_HOUR = int(os.getenv("CHAT_LIMIT_PER_HOUR", "30"))         # per visitor
CHAT_PER_DAY = int(os.getenv("CHAT_LIMIT_PER_DAY", "500"))          # for everyone together
TOKEN_NODES = {"status_agent", "generate"}
REF_RE = re.compile(r"^ET-\d{3,6}$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

app = FastAPI(title="TransitDesk API", version="1.0")

try:
    if db.ensure_schema():                   # a brand-new database gets the demo data
        print("Database was empty: created tables and loaded the demo data.")
except Exception as e:                       # don't block start-up; /health will show the problem
    print("could not prepare the database:", e)


# ======================= helpers =======================
def config_for(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def event(**data) -> str:
    return json.dumps(data, default=str) + "\n"


def require_staff(x_staff_key: str = Header(default="")) -> None:
    if not STAFF_KEY or x_staff_key != STAFF_KEY:
        raise HTTPException(status_code=401, detail="Staff key required")


def allow_read(x_staff_key: str = Header(default="")) -> None:
    """Reading demo data: staff key, or anyone when PUBLIC_READ=true."""
    if not PUBLIC_READ:
        require_staff(x_staff_key)


def short(value, limit: int = 400) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= limit else text[:limit] + "..."


# ======================= passenger side =======================
class ChatIn(BaseModel):
    thread_id: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=2000)


def run_stream(graph_input, config: dict):
    """Yield NDJSON events while the graph runs, including tool calls and their results,
    so the console can show exactly which data the agent used."""
    streamed = False
    try:
        for namespace, mode, chunk in graph.stream(graph_input, config,
                                                   stream_mode=["updates", "messages"],
                                                   subgraphs=True):
            if mode == "updates":
                parent = namespace[0].split(":")[0] + "/" if namespace else ""
                for node, update in chunk.items():
                    if node == "__interrupt__":
                        continue
                    yield event(type="node", node=parent + node)
                    messages = (update or {}).get("messages", []) if isinstance(update, dict) else []
                    for m in messages:
                        if getattr(m, "tool_calls", None):
                            for call in m.tool_calls:
                                yield event(type="tool_call", name=call["name"], args=call["args"])
                        if getattr(m, "type", "") == "tool":
                            yield event(type="tool_result", name=m.name, content=short(m.content))
            else:
                piece, meta = chunk
                if meta.get("langgraph_node") in TOKEN_NODES and piece.text:
                    streamed = True
                    yield event(type="token", text=piece.text)

        values = graph.get_state(config).values
        pending = pending_requests(config)
        if pending:
            yield event(type="approval_needed", booking_ref=pending[0]["booking_ref"],
                        category=values.get("category"), booking_ref_state=values.get("booking_ref"))
        else:
            yield event(type="done", category=values.get("category"),
                        booking_ref=values.get("booking_ref"),
                        reply=values["messages"][-1].text, streamed=streamed)
    except Exception as e:                       # the stream has started: report, don't crash
        yield event(type="error", message=str(e)[:300])


def check_rate_limit(request: Request) -> None:
    """The public chat spends our LLM key, so limit it per visitor and per day.
    Visitors are identified by a hash of their IP address; the IP itself is never stored."""
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")
    ip_hash = hashlib.sha256((STAFF_KEY + ip).encode()).hexdigest()[:32]
    now = int(time.time())
    hour = db.query("SELECT COUNT(*) AS n FROM chat_usage WHERE ip_hash = ? AND at_epoch > ?",
                    (ip_hash, now - 3600))[0]["n"]
    if hour >= CHAT_PER_HOUR:
        raise HTTPException(status_code=429, detail="You've reached the demo limit for this hour. "
                                                    "Please try again later.")
    day = db.query("SELECT COUNT(*) AS n FROM chat_usage WHERE at_epoch > ?", (now - 86400,))[0]["n"]
    if day >= CHAT_PER_DAY:
        raise HTTPException(status_code=429, detail="The demo has reached its daily limit. "
                                                    "Please try again tomorrow.")
    db.execute("INSERT INTO chat_usage VALUES (?, ?)", (ip_hash, now))
    db.execute("DELETE FROM chat_usage WHERE at_epoch < ?", (now - 2 * 86400,))   # keep it small


@app.post("/chat")
def chat(body: ChatIn, request: Request):
    config = config_for(body.thread_id)
    if pending_requests(config):
        raise HTTPException(status_code=409,
                            detail="A cancellation in this conversation is waiting for staff approval.")
    check_rate_limit(request)
    return StreamingResponse(run_stream({"messages": [("human", body.message)]}, config),
                             media_type="application/x-ndjson")


@app.get("/threads/{thread_id}")
def get_thread(thread_id: str):
    config = config_for(thread_id)
    values = graph.get_state(config).values
    messages = [{"role": m.type, "text": m.text} for m in values.get("messages", [])
                if m.type in ("human", "ai") and m.text]
    return {"thread_id": thread_id, "category": values.get("category"),
            "booking_ref": values.get("booking_ref"), "urgent": values.get("urgent"),
            "waiting_for_approval": bool(pending_requests(config)), "messages": messages}


# ======================= staff: approvals =======================
class Decision(BaseModel):
    approved: bool
    note: str = ""
    confirm_ref: str = ""     # required when the request carries a warning


MEMORY_DB = db.DATA_DIR / "memory.db"


def conversation_ids() -> list[str]:
    """All saved conversations, except evaluation runs (their requests are never real).
    A brand-new database has no checkpoint tables until the first conversation is saved."""
    sql = "SELECT DISTINCT thread_id FROM checkpoints"
    try:
        if db.USE_POSTGRES:
            ids = [r["thread_id"] for r in db.query(sql)]
        else:
            with sqlite3.connect(MEMORY_DB) as con:      # own short connection
                ids = [r[0] for r in con.execute(sql).fetchall()]
    except Exception:
        return []
    return [i for i in ids if not i.startswith("eval-")]


@app.get("/approvals", dependencies=[Depends(require_staff)])
def all_approvals():
    items = []
    for thread_id in conversation_ids():
        for request in pending_requests(config_for(thread_id)):
            items.append({"thread_id": thread_id, **request})
    return {"pending": items}


@app.get("/approvals/{thread_id}", dependencies=[Depends(require_staff)])
def get_approvals(thread_id: str):
    return {"pending": pending_requests(config_for(thread_id))}


@app.post("/approvals/{thread_id}", dependencies=[Depends(require_staff)])
def decide(thread_id: str, decision: Decision):
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
    return {"thread_id": thread_id, "reply": out["messages"][-1].text}


# ======================= staff: bookings CRUD =======================
class BookingIn(BaseModel):
    ref: str
    passenger: str = Field(min_length=2, max_length=80)
    hotel: str
    night: str
    status: Literal["CONFIRMED", "PENDING", "CANCELLED"]
    pickup_time: Optional[str] = None
    onward_flight: str = Field(default="", max_length=60)

    @field_validator("ref")
    @classmethod
    def check_ref(cls, v: str) -> str:
        v = v.strip().upper()
        if not REF_RE.match(v):
            raise ValueError("Reference must look like ET-1234")
        return v

    @field_validator("night")
    @classmethod
    def check_night(cls, v: str) -> str:
        if not DATE_RE.match(v):
            raise ValueError("Night must be a date like 2026-11-20")
        return v

    @field_validator("pickup_time")
    @classmethod
    def check_time(cls, v: Optional[str]) -> Optional[str]:
        if v in (None, ""):
            return None
        if not TIME_RE.match(v):
            raise ValueError("Pickup time must be HH:MM, for example 21:30")
        return v


def ensure_hotel(name: str) -> None:
    if not db.query("SELECT 1 FROM hotels WHERE name = ?", (name,)):
        raise HTTPException(status_code=422, detail=f"Unknown hotel '{name}'. Add it under Hotels first.")


@app.get("/api/bookings", dependencies=[Depends(allow_read)])
def list_bookings(q: str = "", status: str = ""):
    sql = "SELECT * FROM bookings WHERE 1=1"
    params: list = []
    if q:
        sql += " AND (ref LIKE ? OR passenger LIKE ? OR hotel LIKE ? OR onward_flight LIKE ?)"
        params += [f"%{q}%"] * 4
    if status:
        sql += " AND status = ?"
        params.append(status.upper())
    return db.query(sql + " ORDER BY night, ref", tuple(params))


@app.post("/api/bookings", status_code=201, dependencies=[Depends(require_staff)])
def create_booking(b: BookingIn):
    ensure_hotel(b.hotel)
    try:
        db.execute("INSERT INTO bookings VALUES (?,?,?,?,?,?,?)",
                   (b.ref, b.passenger, b.hotel, b.night, b.status, b.pickup_time, b.onward_flight))
    except db.IntegrityError:
        raise HTTPException(status_code=409, detail=f"Booking {b.ref} already exists.")
    return db.query("SELECT * FROM bookings WHERE ref = ?", (b.ref,))[0]


@app.put("/api/bookings/{ref}", dependencies=[Depends(require_staff)])
def update_booking(ref: str, b: BookingIn):
    ref = ref.upper()
    if b.ref != ref:
        raise HTTPException(status_code=422, detail="The reference cannot be changed.")
    ensure_hotel(b.hotel)
    changed = db.execute(
        "UPDATE bookings SET passenger=?, hotel=?, night=?, status=?, pickup_time=?, onward_flight=? "
        "WHERE ref = ?",
        (b.passenger, b.hotel, b.night, b.status, b.pickup_time, b.onward_flight, ref))
    if not changed:
        raise HTTPException(status_code=404, detail=f"No booking {ref}.")
    return db.query("SELECT * FROM bookings WHERE ref = ?", (ref,))[0]


@app.delete("/api/bookings/{ref}", dependencies=[Depends(require_staff)])
def delete_booking(ref: str):
    if not db.execute("DELETE FROM bookings WHERE ref = ?", (ref.upper(),)):
        raise HTTPException(status_code=404, detail=f"No booking {ref}.")
    return {"deleted": ref.upper()}


# ======================= staff: hotels CRUD =======================
class HotelIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    location: str = Field(min_length=2, max_length=120)
    shuttle: str = Field(min_length=2, max_length=160)
    phone: str = Field(default="", max_length=30)


@app.get("/api/hotels", dependencies=[Depends(allow_read)])
def list_hotels():
    rows = db.query("SELECT h.*, (SELECT COUNT(*) FROM bookings b WHERE b.hotel = h.name) "
                    "AS bookings FROM hotels h ORDER BY name")
    return rows


@app.post("/api/hotels", status_code=201, dependencies=[Depends(require_staff)])
def create_hotel(h: HotelIn):
    try:
        db.execute("INSERT INTO hotels VALUES (?,?,?,?)", (h.name, h.location, h.shuttle, h.phone))
    except db.IntegrityError:
        raise HTTPException(status_code=409, detail=f"Hotel '{h.name}' already exists.")
    return h


@app.put("/api/hotels/{name}", dependencies=[Depends(require_staff)])
def update_hotel(name: str, h: HotelIn):
    if h.name != name:
        raise HTTPException(status_code=422, detail="The hotel name cannot be changed.")
    if not db.execute("UPDATE hotels SET location=?, shuttle=?, phone=? WHERE name = ?",
                      (h.location, h.shuttle, h.phone, name)):
        raise HTTPException(status_code=404, detail=f"No hotel '{name}'.")
    return h


@app.delete("/api/hotels/{name}", dependencies=[Depends(require_staff)])
def delete_hotel(name: str):
    used = db.query("SELECT COUNT(*) AS n FROM bookings WHERE hotel = ?", (name,))[0]["n"]
    if used:
        raise HTTPException(status_code=409,
                            detail=f"'{name}' has {used} booking(s). Move or delete them first.")
    if not db.execute("DELETE FROM hotels WHERE name = ?", (name,)):
        raise HTTPException(status_code=404, detail=f"No hotel '{name}'.")
    return {"deleted": name}


@app.post("/api/reset", dependencies=[Depends(require_staff)])
def reset_data():
    """Restore the demo bookings and hotels."""
    db.init_db()
    return {"reset": True}


# ======================= health and the console page =======================
@app.get("/health")
def health():
    try:
        db.query("SELECT 1 AS ok")
        database = "ok"
    except Exception as e:
        database = f"error: {str(e)[:120]}"
    if db.USE_POSTGRES:
        storage = "postgres"
    elif os.getenv("VERCEL"):
        storage = "sqlite in /tmp: TEMPORARY, set DATABASE_URL to keep data"
    else:
        storage = "sqlite"
    return {"database": database, "storage": storage, "llm_providers": available_providers(),
            "staff_key_set": bool(STAFF_KEY), "public_read": PUBLIC_READ}


@app.get("/config")
def public_config():
    """Tells the page what a visitor without the staff key may do."""
    return {"public_read": PUBLIC_READ}


PUBLIC = Path(__file__).with_name("public")      # built by:  cd web && npm run build
PAGE = PUBLIC / "index.html"

# Locally, serve the React build's JS/CSS. On Vercel, the CDN serves public/ directly.
if (PUBLIC / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=PUBLIC / "assets"), name="assets")


@app.get("/", include_in_schema=False)
@app.get("/console", include_in_schema=False)
def console():
    # Locally we serve the file. On Vercel, files in public/ are served by the CDN,
    # so if the file isn't inside the function we send the browser there instead.
    if PAGE.exists():
        return FileResponse(PAGE)
    return RedirectResponse("/index.html")
