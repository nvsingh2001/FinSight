import os
import re

from langchain_community.embeddings import FastEmbedEmbeddings
from langchain_neo4j import Neo4jGraph
from langchain_ollama import ChatOllama
from langchain_qdrant import QdrantVectorStore
from qdrant_client.http import models as qmodels

from agent.prompts import CYPHER_PROMPT, GENERATE_PROMPT, GRADE_PROMPT, ROUTER_PROMPT
from agent.state import AgentState

COLLECTION = "finsight_filings"

FORBIDDEN_CYPHER = re.compile(
    r"\b(CREATE|DELETE|DETACH|MERGE|SET|REMOVE|DROP)\b", re.IGNORECASE
)


class AgentNodes:
    """Node implementations for the FinSight agent graph."""

    def __init__(self) -> None:
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

        self.vectorstore = QdrantVectorStore.from_existing_collection(
            embedding=FastEmbedEmbeddings(model_name="nomic-ai/nomic-embed-text-v1.5"),
            collection_name=COLLECTION,
            url=os.environ["QDRANT_URL"],
            api_key=os.environ["QDRANT_API_KEY"],
        )

        self.graph = Neo4jGraph(
            url=os.environ["NEO4J_URI"],
            username=os.environ["NEO4J_USERNAME"],
            password=os.environ["NEO4J_PASSWORD"],
            database=os.environ["NEO4J_DATABASE"],
        )

    def _ask(self, prompt, llm):
        return llm.invoke(prompt).content.strip()

    def corpus_stats(self):
        companies = self.graph.query(
            "MATCH (c:Company) WHERE c.ticker IS NOT NULL RETURN count(c) AS n"
        )[0]["n"]

        years = self.graph.query(
            "MATCH (c:Company)-[:REPORTED]->(m:FinancialMetric) "
            "WITH c, count(DISTINCT m.fiscal_year) AS y, "
            "     min(m.fiscal_year) AS lo, max(m.fiscal_year) AS hi "
            "RETURN max(y) AS years, min(lo) AS first_year, max(hi) AS last_year"
        )[0]

        client = self.vectorstore.client
        tickers = client.facet(COLLECTION, "metadata.ticker", limit=100, exact=True)
        filings = 0
        for hit in tickers.hits:
            by_ticker = qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="metadata.ticker",
                        match=qmodels.MatchValue(value=hit.value),
                    )
                ]
            )
            filings += len(
                client.facet(
                    COLLECTION,
                    "metadata.fiscal_year",
                    facet_filter=by_ticker,
                    limit=100,
                    exact=True,
                ).hits
            )

        return {
            "companies": companies,
            "filings": filings,
            "fiscal_years": years["years"],
            "first_year": years["first_year"],
            "last_year": years["last_year"],
            "chunks": client.count(COLLECTION).count,
        }

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
            ROUTER_PROMPT.format(question=state["question"]), llm=self.fast_llm
        ).lower()
        tokens = re.findall(r"[a-z]+|\d{4}", answer)

        route = next(
            (t for t in tokens if t in ("vector", "graph", "hybrid")), "hybrid"
        )
        year = next((t for t in tokens if t.isdigit()), "latest")

        return {"route": route, "year": year}

    def retrieve_vector(self, state: AgentState):
        docs = self.vectorstore.similarity_search(
            state["question"],
            k=6,
            filter=self._year_filter(state.get("year", "latest")),
        )
        return {"documents": docs}

    def retrieve_graph(self, state: AgentState):
        cypher = self._ask(
            CYPHER_PROMPT.format(
                schema=self.graph.get_schema, question=state["question"]
            ),
            llm=self.llm,
        )

        cypher = re.sub(r"^```(?:cypher)?|```$", "", cypher, flags=re.MULTILINE).strip()

        if FORBIDDEN_CYPHER.search(cypher):
            return {"graph_results": []}

        try:
            return {"graph_results": self.graph.query(cypher)}
        except Exception as e:
            print(f"cypher failed: {e}")
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
        ).lower()

        return {
            "verdict": verdict if verdict == "retry" else "useful",
            "retry_count": state.get("retry_count", 0) + 1,
        }
