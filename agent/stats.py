from qdrant_client.http import models as qmodels

from agent.connections import COLLECTION


class CorpusStats:
    def __init__(self, connections) -> None:
        self.graph = connections.graph
        self.vectorstore = connections.vectorstore

    def compute(self):
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
                    COLLECTION, "metadata.fiscal_year",
                    facet_filter=by_ticker, limit=100, exact=True,
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
