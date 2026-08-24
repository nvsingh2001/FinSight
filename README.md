# FinSight

A financial research assistant over SEC 10-K filings. Combines vector search (Qdrant) with a knowledge graph (Neo4j), orchestrated by a LangGraph agent that routes each query to the right retrieval path.

Covers the last five annual filings of Apple, Microsoft, and NVIDIA, plus 19
fiscal years of reported financials for each.

- UI: https://finsight-app-ce27.up.railway.app
- API docs: https://finsight-production-f255.up.railway.app/docs

## How it works

Questions fall into two kinds, and they need different retrieval.

"What was NVIDIA's revenue?" wants an exact number. Those live in Neo4j as `FinancialMetric` nodes loaded from the SEC's XBRL API — every fiscal year each company has reported, not just the latest — so the agent writes a Cypher query and reads the value straight from the graph. No arithmetic is done by the model.

"How does Apple describe its supply chain risks?" wants language from the filing. Those chunks live in Qdrant, retrieved by embedding similarity. Five years of filings are indexed, so the router also picks which year to read — the year named in the question, or the latest one — and retrieval is filtered to it.

Anything that needs both — comparing R&D spend and explaining what drives it — runs both paths and merges the results.

A router classifies each question, retrieval runs, an answer is generated from the retrieved context only, and a grader checks the answer against that context. If the grader rejects it, the question is re-routed and tried again, up to two attempts.

```
question -> route -+-> vector search (Qdrant) --+-> generate -> grade -+-> answer
                   +-> Cypher query (Neo4j) ----+                      |
                   ^                                                   |
                   +------------------ retry (max 2) ------------------+
```

## Layout

```
ingestion/    fetch filings, parse sections, chunk and embed, build the graph
agent/        state, prompts, nodes, and the LangGraph wiring
api/          FastAPI service
ui/           Streamlit client
```

## Setup

```bash
python -m venv finsight
source finsight/bin/activate
pip install -r requirements.txt
```

Create a `.env` with:

```
OLLAMA_API_KEY=
QDRANT_URL=
QDRANT_API_KEY=
NEO4J_URI=
NEO4J_USERNAME=
NEO4J_PASSWORD=
NEO4J_DATABASE=
```

## Building the data

Run from the repo root, in order:

```bash
python -m ingestion.fetch_filings           # download the last five 10-Ks for each ticker
python -m ingestion.chunk_and_embed --embed # parse sections, chunk, push to Qdrant
python -m ingestion.load_financials         # XBRL metrics into Neo4j
python -m ingestion.extract_graph           # entities and relationships into Neo4j
```

`extract_graph` makes one LLM call per chunk and takes several minutes.

## Running

```bash
uvicorn api.main:app --reload
streamlit run ui/app.py
```

The UI reads `FINSIGHT_API_URL` and falls back to `http://localhost:8000`.

The API exposes `POST /query` for a single JSON response and `POST /query/stream` for newline-delimited events (`progress`, `token`, `revising`, `done`).

```bash
curl -X POST localhost:8000/query \
  -H 'content-type: application/json' \
  -d '{"question": "What was NVIDIA'\''s revenue in its latest fiscal year?"}'
```

## Things to try

- What was NVIDIA's revenue in its latest fiscal year?
- How does Apple describe its supply chain risks?
- How has NVIDIA's revenue changed since 2020?
- What risks did Apple flag in fiscal 2022?
- Compare R&D spending across the three companies and explain what drives it.
- How much did Microsoft spend on R&D, and what risks does it see in its AI investments?

## Deployment

Both services deploy from `main` on Railway using the Dockerfile, which bakes the embedding model into the image so containers start without downloading it. The API needs about 1 GB of memory, most of it the embedding model.

## Notes

Filing text is extracted by following each document's own table-of-contents anchors, with a heading-pattern fallback for filings that don't link their sections. Fiscal years differ across the three companies, so metrics are matched to the exact period end date reported in each filing.

Generated Cypher is checked for write clauses before it runs, and answers are limited to the retrieved context — the agent says so when a question can't be answered from the filings.
