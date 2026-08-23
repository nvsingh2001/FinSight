import json
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

from ingestion.fetch_filings import EdgarClient

CONCEPTS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"],
    "net_income": ["NetIncomeLoss"],
    "rnd_expense": ["ResearchAndDevelopmentExpense"],
}


class FinancialsExtractor:
    """Pulls annual metrics for one fiscal year out of a CompanyFacts response."""

    @staticmethod
    def _annual_value(concept_data, report_date):
        for entry in concept_data["units"]["USD"]:
            if (
                entry.get("form") == "10-K"
                and entry.get("end") == report_date
                and "start" in entry
                and (
                    date.fromisoformat(entry["end"])
                    - date.fromisoformat(entry["start"])
                ).days
                > 300
            ):
                return entry["val"]

        return None

    def extract(self, facts, report_date):
        gaap = facts["facts"]["us-gaap"]
        metrics = {}
        for metric, candidates in CONCEPTS.items():
            value = None
            for concept in candidates:
                if concept in gaap:
                    value = self._annual_value(gaap[concept], report_date)
                    if value is not None:
                        break
            if value is None:
                print(f"  warning: no value found for {metric}")
                continue
            metrics[metric] = value

        return metrics


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

    def load(self, ticker, name, cik, fiscal_year, metrics):
        for metric, value in metrics.items():
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
        for ticker, meta in metadata.items():
            facts = client.company_facts(meta["cik"])
            metrics = extractor.extract(facts, meta["report_date"])
            loader.load(
                ticker, facts["entityName"], meta["cik"], meta["fiscal_year"], metrics
            )
            print(f"{ticker}: {metrics}")
    finally:
        loader.close()


if __name__ == "__main__":
    main()
