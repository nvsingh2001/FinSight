import json
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent.graph import build_graph
from agent.nodes import AgentNodes


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    nodes = AgentNodes()
    app.state.agent = build_graph(nodes)

    try:
        app.state.stats = nodes.corpus_stats()
    except Exception as e:
        print(f"corpus stats unavailable: {e}")
        app.state.stats = None

    yield


app = FastAPI(
    title="FinSight",
    description="Hybrid RAG + Knowledge graph copilot over SEC 10-K filings",
    lifespan=lifespan,
)

NODE_LABELS = {
    "route": "routing the question",
    "retrieve_vector": "searching filings",
    "retrieve_graph": "querying knowledge graph",
    "generate": "drafting answer",
    "grade": "checking answer against sources",
}


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class QueryResponse(BaseModel):
    answer: str
    route: str
    year: str
    retries: int


class StatsResponse(BaseModel):
    companies: int
    filings: int
    fiscal_years: int
    first_year: str
    last_year: str
    chunks: int


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats", response_model=StatsResponse)
def stats(request: Request):
    if request.app.state.stats is None:
        raise HTTPException(status_code=503, detail="corpus stats unavailable")
    return request.app.state.stats


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest, request: Request):
    result = request.app.state.agent.invoke(
        {"question": req.question, "retry_count": 0}
    )
    return QueryResponse(
        answer=result["generation"],
        route=result["route"],
        year=result["year"],
        retries=result["retry_count"],
    )


@app.post("/query/stream")
async def query_stream(req: QueryRequest, request: Request):
    agent = request.app.state.agent

    async def events():
        last_node = None
        streamed = False
        final = {}

        async for ev in agent.astream_events(
            {"question": req.question, "retry_count": 0}, version="v2"
        ):
            kind = ev["event"]
            node = ev.get("metadata", {}).get("langgraph_node")

            if kind == "on_chain_start" and node in NODE_LABELS and node != last_node:
                last_node = node
                if node == "route" and streamed:
                    streamed = False
                    yield json.dumps({"type": "revising"}) + "\n"
                yield (
                    json.dumps({"type": "progress", "stage": NODE_LABELS[node]}) + "\n"
                )
            elif kind == "on_chat_model_stream" and node == "generate":
                text = ev["data"]["chunk"].content
                if text:
                    streamed = True
                    yield json.dumps({"type": "token", "text": text}) + "\n"

            elif kind == "on_chain_end" and ev.get("name") == "LangGraph":
                final = ev["data"]["output"]

        yield json.dumps(
            {
                "type": "done",
                "route": final.get("route"),
                "year": final.get("year"),
                "retries": final.get("retry_count", 0),
            }
        ) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")
