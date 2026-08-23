from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from pydantic import BaseModel, Field

from agent.graph import build_graph


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    app.state.agent = build_graph()
    yield


app = FastAPI(
    title="FinSight",
    description="Hybrid RAG + Knowledge graph copilot over SEC 10-K filings",
    lifespan=lifespan,
)


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class QueryResponse(BaseModel):
    answer: str
    route: str
    retries: int


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest, request: Request):
    result = request.app.state.agent.invoke(
        {"question": req.question, "retry_count": 0}
    )
    return QueryResponse(
        answer=result["generation"],
        route=result["route"],
        retries=result["retry_count"],
    )
