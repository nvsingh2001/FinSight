import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.embeddings import FastEmbedEmbeddings
from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client.http import models as qmodels

from ingestion.parser import TenKParser

COLLECTION = "finsight_filings"
INDEXED_FIELDS = {
    "metadata.fiscal_year": qmodels.PayloadSchemaType.KEYWORD,
    "metadata.is_latest": qmodels.PayloadSchemaType.BOOL,
    "metadata.ticker": qmodels.PayloadSchemaType.KEYWORD,
}


class IngestionPipeline:
    def __init__(
        self,
        raw_dir="data/raw",
        processed_dir="data/processed",
        chunk_size=1000,
        chunk_overlap=150,
    ):
        self.raw_dir = Path(raw_dir)
        self.processed_dir = Path(processed_dir)
        self.parser = TenKParser()
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )

    def build_chunks(self):
        metadata = json.loads((self.raw_dir / "metadata.json").read_text())
        docs = []

        for ticker, filings in metadata.items():
            latest = max(f["fiscal_year"] for f in filings)

            for meta in filings:
                html = (self.raw_dir / meta["file"]).read_text()
                sections = self.parser.parse(html)
                print(f"{ticker} FY{meta['fiscal_year']}: {len(sections)} sections")

                for name, body in sections.items():
                    for chunk in self.splitter.split_text(body):
                        docs.append(
                            Document(
                                page_content=chunk,
                                metadata={
                                    "ticker": ticker,
                                    "section": name,
                                    "fiscal_year": meta["fiscal_year"],
                                    "is_latest": meta["fiscal_year"] == latest,
                                },
                            )
                        )

        print(f"total chunks: {len(docs)}")
        return docs

    def save(self, docs):
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        payload = [{"text": d.page_content, "metadata": d.metadata} for d in docs]
        (self.processed_dir / "chunks.json").write_text(json.dumps(payload, indent=2))

    def embed(self, docs):
        store = QdrantVectorStore.from_documents(
            docs,
            FastEmbedEmbeddings(model_name="nomic-ai/nomic-embed-text-v1.5"),
            url=os.environ["QDRANT_URL"],
            api_key=os.environ["QDRANT_API_KEY"],
            collection_name=COLLECTION,
            force_recreate=True,
        )

        for field, schema in INDEXED_FIELDS.items():
            store.client.create_payload_index(COLLECTION, field, field_schema=schema)

        print("Embedded into qdrant")


def main():
    load_dotenv()
    pipeline = IngestionPipeline()
    docs = pipeline.build_chunks()
    pipeline.save(docs=docs)
    if "--embed" in sys.argv:
        pipeline.embed(docs=docs)


if __name__ == "__main__":
    main()
