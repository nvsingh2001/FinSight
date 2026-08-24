from typing import Literal, TypedDict

from langchain_core.documents import Document


class AgentState(TypedDict):
    question: str
    year: str
    route: Literal["vector", "graph", "hybrid"]
    documents: list[Document]
    graph_results: list[dict]
    generation: str
    retry_count: int
    verdict: Literal["useful", "retry"]
