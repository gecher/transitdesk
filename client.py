"""A tiny terminal client for api.py that prints tokens as they arrive."""
import json
import sys
import uuid

import httpx

API = "http://127.0.0.1:8000"
thread = sys.argv[1] if len(sys.argv) > 1 else uuid.uuid4().hex[:8]
print(f"TransitDesk via API  (thread: {thread})   type /quit to stop")


def send(text: str) -> None:
    with httpx.stream("POST", f"{API}/chat", json={"thread_id": thread, "message": text},
                      timeout=120) as response:
        if response.status_code != 200:
            response.read()
            print(f"Desk: [{response.status_code}] {response.json()['detail']}")
            return
        print("Desk: ", end="", flush=True)
        nodes = []
        for line in response.iter_lines():
            if not line:
                continue
            e = json.loads(line)
            if e["type"] == "node":
                nodes.append(e["node"])
            elif e["type"] == "token":
                print(e["text"], end="", flush=True)
            elif e["type"] == "approval_needed":
                print(f"Your request for {e['booking_ref']} is waiting for staff approval.", end="")
            elif e["type"] == "done" and not e["streamed"]:
                print(e["reply"], end="")
            elif e["type"] == "error":
                print(f"[error] {e['message']}", end="")
        print(f"\n      path: {' -> '.join(nodes)}")


while True:
    text = input("\nYou: ").strip()
    if text == "/quit":
        break
    if not text:
        continue
    try:
        send(text)
    except httpx.ConnectError:
        print("Desk: [cannot reach the API] Is it running?  uvicorn api:app --reload")
