import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import requests

TICKERS = ["AAPL", "MSFT", "NVDA"]


@dataclass
class Filing:
    ticker: str
    cik: int
    accession: str
    primary_doc: str
    report_date: str

    @property
    def fiscal_year(self):
        return self.report_date[:4]

    @property
    def filename(self):
        return f"{self.ticker}_10-K_{self.fiscal_year}.html"


class EdgarClient:
    """Minimal SEC EDGAR client for fetching 10-K filings."""

    TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
    SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
    ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{doc}"

    def __init__(self, user_agent, request_delay=0.2):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self.request_delay = request_delay
        self._cik_map = None

    def _get(self, url):
        time.sleep(self.request_delay)
        resp = self.session.get(url)
        resp.raise_for_status()
        return resp

    @property
    def cik_map(self):
        if self._cik_map is None:
            data = self._get(self.TICKER_MAP_URL).json()
            self._cik_map = {e["ticker"]: e["cik_str"] for e in data.values()} 
        return self._cik_map

    def latest_10k(self, ticker):
        cik = self.cik_map[ticker]
        url = self.SUBMISSIONS_URL.format(cik=cik)
        recent = self._get(url).json()["filings"]["recent"]

        for i, form in enumerate(recent["form"]):
            if form == "10-K":
                return Filing(
                    ticker=ticker,
                    cik=cik,
                    accession=recent["accessionNumber"][i],
                    primary_doc=recent["primaryDocument"][i],
                    report_date=recent["reportDate"][i],
                )

        raise ValueError(f"no 10-K found for {ticker}")

    def download(self, filing):
        url = self.ARCHIVES_URL.format(
            cik=filing.cik,
            accession=filing.accession.replace("-", ""),
            doc=filing.primary_doc,
        )
        return self._get(url).text


def main():
    raw_dir = Path("data/raw")
    raw_dir.mkdir(parents=True, exist_ok=True)

    client = EdgarClient(user_agent="Naman Vinay Singh namanvinaysingh24@gmail.com")
    metadata = {}

    for ticker in TICKERS:
        filing = client.latest_10k(ticker)
        html = client.download(filing)

        (raw_dir / filing.filename).write_text(html)
        metadata[ticker] = asdict(filing) | {"file": filing.filename}
        print(f"{ticker}: saved {filing.filename} ({len(html) // 1024} KB)")

    (raw_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
