"""Step 7a: streaming in the terminal.

Instead of waiting for the whole answer, we watch the graph run:
- stream_mode="updates"  -> which node just finished
- stream_mode="messages" -> LLM tokens as they are generated
- subgraphs=True         -> include the RAG graph that runs inside the policy node
"""
import sys
import time

from step6_desk import graph, pending_requests

# Only show tokens from nodes that write the final answer.
# (classify / grade / rewrite also produce tokens, but those are JSON, not for passengers.)
TOKEN_NODES = {"status_agent", "generate"}


def run(thread_id: str, text: str) -> None:
    config = {"configurable": {"thread_id": thread_id}}
    print(f"\nYou: {text}")
    print("Desk: ", end="", flush=True)

    start = time.perf_counter()
    first_token_at = None
    nodes = []
    # subgraphs=True: also stream from graphs running INSIDE a node (the policy RAG graph).
    # Each item is (namespace, mode, chunk); namespace is () for the main graph,
    # or ("policy:<id>",) for the RAG graph running inside the policy node.
    for namespace, mode, chunk in graph.stream({"messages": [("human", text)]}, config,
                                               stream_mode=["updates", "messages"],
                                               subgraphs=True):
        if mode == "updates":                      # chunk = {node_name: what it returned}
            parent = namespace[0].split(":")[0] + "/" if namespace else ""
            nodes.extend(parent + n for n in chunk if n != "__interrupt__")
        elif mode == "messages":                   # chunk = (message_piece, metadata)
            piece, meta = chunk
            if meta.get("langgraph_node") in TOKEN_NODES and piece.text:
                if first_token_at is None:
                    first_token_at = time.perf_counter() - start
                print(piece.text, end="", flush=True)

    if pending_requests(config):
        print("I've sent your request to a staff member for approval.", end="")
    elif first_token_at is None:                   # nodes without an LLM (other, complaint...)
        print(graph.get_state(config).values["messages"][-1].text, end="")

    total = time.perf_counter() - start
    first = f"first token {first_token_at:.1f}s, " if first_token_at else ""
    print(f"\n      path: {' -> '.join(nodes)}   ({first}total {total:.1f}s)")


if __name__ == "__main__":
    thread = sys.argv[1] if len(sys.argv) > 1 else "stream-demo"
    for message in [
        "hi",
        "Is booking ET-3301 confirmed, and how do I get to the hotel?",
        "Can anyone get a free hotel for a 10-hour connection?",
    ]:
        run(thread, message)
