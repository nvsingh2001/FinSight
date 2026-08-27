import os

from langchain_community.embeddings import FastEmbedEmbeddings
from langchain_neo4j import Neo4jGraph
from langchain_qdrant import QdrantVectorStore
from langfuse import get_client
from langfuse.langchain import CallbackHandler

COLLECTION = "finsight_filings"


class GraphConnections:
    def __init__(self) -> None:
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

        self.langfuse = get_client()
        self.langfuse_handler = CallbackHandler()
