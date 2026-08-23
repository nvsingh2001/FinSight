from langgraph.graph import END, START, StateGraph

from agent.nodes import AgentNodes
from agent.state import AgentState

MAX_RETRIES = 2


def _after_route(state: AgentState):
    return state["route"]


def _after_vector(state: AgentState):
    return "retrieve_graph" if state["route"] == "hybrid" else "generate"


def _after_grade(state: AgentState):
    if state["verdict"] == "useful" or state["retry_count"] >= MAX_RETRIES:
        return "end"
    return "retry"


def build_graph():
    nodes = AgentNodes()
    workflow = StateGraph(AgentState)

    workflow.add_node("route", nodes.route)
    workflow.add_node("retrieve_vector", nodes.retrieve_vector)
    workflow.add_node("retrieve_graph", nodes.retrieve_graph)
    workflow.add_node("generate", nodes.generate)
    workflow.add_node("grade", nodes.grade)

    workflow.add_edge(START, "route")
    workflow.add_conditional_edges(
        "route",
        _after_route,
        {
            "vector": "retrieve_vector",
            "hybrid": "retrieve_vector",
            "graph": "retrieve_graph",
        },
    )
    workflow.add_conditional_edges(
        "retrieve_vector",
        _after_vector,
        {"retrieve_graph": "retrieve_graph", "generate": "generate"},
    )
    workflow.add_edge("retrieve_graph", "generate")
    workflow.add_edge("generate", "grade")
    workflow.add_conditional_edges(
        "grade", _after_grade, {"end": END, "retry": "route"}
    )

    return workflow.compile()


def main():
    from dotenv import load_dotenv

    load_dotenv()
    agent = build_graph()

    questions = [
        "What was NVIDIA's revenue in its latest fiscal year?",
        "How does Apple describe its supply chain risks?",
        "Compare R&D spending across the three companies and explain what drives it.",
    ]

    for q in questions:
        result = agent.invoke({"question": q, "retry_count": 0})
        print(f"\nQ: {q}")
        print(f"route={result['route']} retries={result['retry_count']}")
        print(result["generation"])


if __name__ == "__main__":
    main()
