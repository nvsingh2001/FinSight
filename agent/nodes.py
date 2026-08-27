import os
import re

from langchain_ollama import ChatOllama
from qdrant_client.http import models as qmodels

from agent.connections import GraphConnections
from agent.prompts import CYPHER_PROMPT, GENERATE_PROMPT, GRADE_PROMPT, ROUTER_PROMPT
from agent.state import AgentState

FORBIDDEN_CYPHER = re.compile(
    r"\b(CREATE|DELETE|DETACH|MERGE|SET|REMOVE|DROP)\b", re.IGNORECASE
)


class AgentNodes:
    """Node implementations for the FinSight agent graph."""

    def __init__(self, connections=None) -> None:
        self.llm = ChatOllama(
            model="gpt-oss:120b-cloud",
            base_url="https://ollama.com",
            client_kwargs={
                "headers": {"Authorization": f"Bearer {os.environ['OLLAMA_API_KEY']}"}
            },
            temperature=0,
        )

        self.fast_llm = ChatOllama(
            model="gpt-oss:20b-cloud",
            base_url="https://ollama.com", client_kwargs={
                "headers": {"Authorization": f"Bearer {os.environ['OLLAMA_API_KEY']}"}
            },
            temperature=0,
        )

        connections = connections or GraphConnections()
        self.vectorstore = connections.vectorstore
        self.graph = connections.graph
        self.langfuse = connections.langfuse

    def _ask(self, prompt, llm, name):
        return llm.invoke(prompt, config={"run_name": name}).content.strip()

    def _year_filter(self, year):
        if year == "latest":
            return qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="metadata.is_latest", match=qmodels.MatchValue(value=True)
                    )
                ]
            )
        return qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="metadata.fiscal_year", match=qmodels.MatchValue(value=year)
                )
            ]
        )

    def route(self, state: AgentState):
        answer = self._ask(
            ROUTER_PROMPT.format(question=state["question"]),
            llm=self.fast_llm,
            name="route-classify",
        ).lower()
        tokens = re.findall(r"[a-z]+|\d{4}", answer)

        route = next(
            (t for t in tokens if t in ("vector", "graph", "hybrid")), "hybrid"
        )
        year = next((t for t in tokens if t.isdigit()), "latest")

        return {"route": route, "year": year}

    def retrieve_vector(self, state: AgentState):
        year = state.get("year", "latest")
        with self.langfuse.start_as_current_observation(
            as_type="retriever",
            name="vector-search",
            input={"question": state["question"], "year": year},
        ) as obs:
            docs = self.vectorstore.similarity_search(
                state["question"], k=6, filter=self._year_filter(year)
            )
            obs.update(
                output=[
                    {
                        "ticker": d.metadata.get("ticker"),
                        "fiscal_year": d.metadata.get("fiscal_year"),
                        "section": d.metadata.get("section"),
                    }
                    for d in docs
                ]
            )
        return {"documents": docs}

    def retrieve_graph(self, state: AgentState):
        cypher = self._ask(
            CYPHER_PROMPT.format(
                schema=self.graph.get_schema, question=state["question"]
            ),
            llm=self.llm,
            name="generate-cypher",
        )

        cypher = re.sub(r"^```(?:cypher)?|```$", "", cypher, flags=re.MULTILINE).strip()

        with self.langfuse.start_as_current_observation(
            as_type="retriever", name="graph-query", input=cypher
        ) as obs:
            if FORBIDDEN_CYPHER.search(cypher):
                obs.update(output=[], metadata={"blocked": "forbidden_cypher"})
                return {"graph_results": []}

            try:
                results = self.graph.query(cypher)
                obs.update(output=results)
                return {"graph_results": results}
            except Exception as e:
                print(f"cypher failed: {e}")
                obs.update(output=[], metadata={"error": str(e)})
                return {"graph_results": []}

    def generate(self, state: AgentState):
        docs = "\n\n".join(
            f"[{d.metadata['ticker']} FY{d.metadata['fiscal_year']} / {d.metadata['section']}]"
            f"\n{d.page_content}"
            for d in state.get("documents", [])
        )

        answer = self._ask(
            GENERATE_PROMPT.format(
                graph_results=state.get("graph_results", []) or "none",
                documents=docs or "none",
                question=state["question"],
            ),
            llm=self.llm,
            name="generate-answer",
        )

        return {"generation": answer}

    def grade(self, state: AgentState):
        context = f"{state.get('graph_results', [])}\n{state.get('documents', [])}"
        verdict = self._ask(
            GRADE_PROMPT.format(
                question=state["question"],
                context=context[:6000],
                generation=state["generation"],
            ),
            llm=self.fast_llm,
            name="grade-verdict",
        ).lower()

        return {
            "verdict": verdict if verdict == "retry" else "useful",
            "retry_count": state.get("retry_count", 0) + 1,
        }
