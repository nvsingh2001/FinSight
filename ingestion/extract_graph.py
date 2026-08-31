import json
import os
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_experimental.graph_transformers import LLMGraphTransformer
from langchain_neo4j import Neo4jGraph
from langchain_ollama import ChatOllama

SECTIONS = ["risk_factors", "mdna"]

ALLOWED_NODES = ["Company", "Product", "Risk", "Market", "Technology"]

ALLOWED_RELATIONSHIPS = [
    ("Company", "FACES_RISK", "Risk"),
    ("Company", "COMPETES_WITH", "Company"),
    ("Company", "OFFERS", "Product"),
    ("Company", "OPERATES_IN", "Market"),
    ("Company", "DEPENDS_ON", "Technology"),
]

ALIASES = {
    "AAPL": ["apple", "apple inc.", "apple inc"],
    "MSFT": ["microsoft", "microsoft corporation", "microsoft corp"],
    "NVDA": ["nvidia", "nvidia corporation", "nvidia corp"],
}

NAMES = {"AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA"}


class GraphExtractor:
    """LLM-extracts entities/relationships from filing chunks into Neo4j."""

    def __init__(self, chunks_path="data/processed/chunks.json", per_company_cap=25):
        self.chunks_path = Path(chunks_path)
        self.per_company_cap = per_company_cap

        llm = ChatOllama(
            model="gpt-oss:120b-cloud",
            base_url="https://ollama.com",
            client_kwargs={
                "headers": {"Authorization": f"Bearer {os.environ['OLLAMA_API_KEY']}"}
            },
            temperature=0,
        )

        self.transformer = LLMGraphTransformer(
            llm=llm,
            allowed_nodes=ALLOWED_NODES,
            allowed_relationships=ALLOWED_RELATIONSHIPS,
            ignore_tool_usage=True,
            additional_instructions=(
                "Always refer to companies by their proper name (e.g. 'Apple', "
                "'NVIDIA'), never as 'the Company'. Do not extract section "
                "headings or generic labels like 'Risk Factors' as entities."
            ),
        )

        self.graph = Neo4jGraph(
            url=os.environ["NEO4J_URI"],
            username=os.environ["NEO4J_USERNAME"],
            password=os.environ["NEO4J_PASSWORD"],
            database=os.environ["NEO4J_DATABASE"],
        )

    def load_documents(self):
        chunks = json.loads(self.chunks_path.read_text())
        taken = defaultdict(int)
        docs = []
        for chunk in chunks:
            meta = chunk["metadata"]
            if meta["section"] not in SECTIONS:
                continue
            if taken[meta["ticker"]] >= self.per_company_cap:
                continue
            taken[meta["ticker"]] += 1

            name = NAMES[meta["ticker"]]
            text = (
                f"[Excerpt from {name}'s 10-K annual report. "
                f"'The Company' and 'we' refer to {name}.]\n\n" + chunk["text"]
            )
            docs.append(Document(page_content=text, metadata=meta))

        return docs

    def extract(self, docs):
        graph_docs = []
        for i, doc in enumerate(docs, 1):
            result = self.transformer.convert_to_graph_documents([doc])
            graph_docs.extend(result)
            rels = sum(len(gd.relationships) for gd in result)
            print(f"[{i}/{len(docs)}] {doc.metadata['ticker']}: {rels} relationships")

        return graph_docs

    def write(self, graph_docs):
        self.graph.add_graph_documents(
            graph_docs, baseEntityLabel=True, include_source=True
        )

    def link_companies(self):
        for ticker, aliases in ALIASES.items():
            self.graph.query(
                """
                MATCH (c:Company {ticker: $ticker})
                MATCH (e:__Entity__) WHERE toLower(e.id) IN $aliases
                MERGE (c)-[:SAME_AS]->(e)
                """,
                {"ticker": ticker, "aliases": aliases},
            )

    def report(self):
        counts = self.graph.query(
            "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n ORDER BY n DESC"
        )
        for row in counts:
            print(f"{row['label']}: {row['n']}")


def main():
    load_dotenv()
    extractor = GraphExtractor()

    docs = extractor.load_documents()
    print(f"extracting from {len(docs)} chunks...")

    graph_docs = extractor.extract(docs)
    extractor.write(graph_docs)
    extractor.link_companies()
    extractor.report()


if __name__ == "__main__":
    main()
