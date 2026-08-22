# FinSight

A financial research assistant over SEC 10-K filings. Combines vector search (Qdrant) with a knowledge graph (Neo4j), orchestrated by a LangGraph agent that routes each query to the right retrieval path.

Work in progress.

## Setup

```bash
python -m venv finsight
source finsight/bin/activate
pip install -r requirements.txt
```
