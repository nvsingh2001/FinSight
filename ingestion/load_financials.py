import json
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

from ingestion.fetch_filings import EdgarClient

CONCEPTS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax","SalesRevenueNet" ,"Revenues"],
    "net_income": ["NetIncomeLoss"],
    "rnd_expense": ["ResearchAndDevelopmentExpense"],
}


class FinancialsExtractor:
    """Pulls annual metrics for one fiscal year out of a CompanyFacts response."""

    @staticmethod
    def _annual_series(concept_data):
        """{fiscal_year: value} for every annual figure reported on a 10-K."""
        values = {}
        for entry in concept_data["units"].get("USD", []):
            if entry.get("form") != "10-K" or "start" not in entry:
                continue
            span = date.fromisoformat(entry["end"]) - date.fromisoformat(entry["start"])
            if span.days <= 300:
                continue
            values[entry["end"][:4]] = entry["val"]
        return values

    def extract(self, facts):
        gaap = facts["facts"]["us-gaap"]
        series = {}
        for metric, candidates in CONCEPTS.items():
            values = {}
            for concept in candidates:
                if concept in gaap:
                    values = self._annual_series(gaap[concept]) | values
            if not values:
                print(f"  warning: no value found for {metric}")
                continue
            series[metric] = values

        return series 


class GraphLoader:
    """Writes companies and their financial metrics into Neo4j."""

    WRITE_METRIC = """
        MERGE (c:Company {ticker: $ticker})
        SET c.name = $name, c.cik = $cik
        MERGE (m:FinancialMetric {ticker: $ticker, name: $metric, fiscal_year: $fy})
        SET m.value = $value, m.unit = 'USD'
        MERGE (c)-[:REPORTED]->(m)
    """

    def __init__(self, uri, username, password):
        self.driver = GraphDatabase.driver(uri, auth=(username, password))

    def close(self):
        self.driver.close()

    def load(self, ticker, name, cik, series):
        for metric, values in series.items():
            for fiscal_year, value in values.items():
                self.driver.execute_query(
                    self.WRITE_METRIC,
                    ticker=ticker,
                    name=name,
                    cik=cik,
                    metric=metric,
                    fy=fiscal_year,
                    value=value,
                )


def main():
    load_dotenv()
    metadata = json.loads(Path("data/raw/metadata.json").read_text())

    client = EdgarClient(user_agent="Naman Vinay Singh namanvinaysingh24@gmail.com")
    extractor = FinancialsExtractor()
    loader = GraphLoader(
        os.environ["NEO4J_URI"],
        os.environ["NEO4J_USERNAME"],
        os.environ["NEO4J_PASSWORD"],
    )

    try:
        for ticker, filings in metadata.items():
            cik = filings[0]["cik"]
            facts = client.company_facts(cik)
            series = extractor.extract(facts)
            loader.load(
                ticker, facts["entityName"], cik, series
            )
            print(f"{ticker}: " + ", ".join(
                f"{m} {min(v)}--{max(v)} ({len(v)}y)" for m,v in series.items()
            ))
    finally:
        loader.close()


if __name__ == "__main__":
    main()
