from langchain_core.messages import SystemMessage
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from llm import get_llm
from tools import TOOLS

SYSTEM = SystemMessage(
    "You are the hotel desk assistant for an airline's transit passengers. "
    "Always use the tools to look up booking and hotel facts; never guess them. "
    "If the passenger gives no booking reference, ask for it. "
    "Answer in one to three short sentences.")

llm_with_tools = get_llm().bind_tools(TOOLS)   # tells the LLM which tools exist


def agent(state: MessagesState) -> dict:
    response = llm_with_tools.invoke([SYSTEM] + state["messages"])
    return {"messages": [response]}             # appended by add_messages


builder = StateGraph(MessagesState)
builder.add_node("agent", agent)
builder.add_node("tools", ToolNode(TOOLS))
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", tools_condition)  # tool calls -> "tools", else END
builder.add_edge("tools", "agent")                        # the loop back
graph = builder.compile()


if __name__ == "__main__":
    questions = [
        "Is booking et-5520 confirmed, and when is my pickup?",
        "Where is the hotel for ET-3301 and how do I get there from the airport?",
        "What's the status of ET-0000?",
        "Is my hotel confirmed?",
    ]
    for q in questions:
        result = graph.invoke({"messages": [("human", q)]})
        print(f"\n=== {q}")
        for m in result["messages"]:
            if m.type == "ai" and m.tool_calls:
                for tc in m.tool_calls:
                    print(f"  [tool call]   {tc['name']}({tc['args']})")
            elif m.type == "tool":
                print(f"  [tool result] {str(m.content)[:110]}")
        print(f"  ANSWER: {result['messages'][-1].text}")