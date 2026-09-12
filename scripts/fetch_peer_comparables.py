"""Rebuild fixtures/peers/lubricants.csv from screener.in (Day 6).

Not part of the comparison module's runtime path - `reverse_dcf.compare`
only reads the committed CSV fixture, same reasoning as
`fetch_market_price.py`. This script exists so the peer figures are
reproducible rather than a one-off hand-copy.

screener.in is a free public equity-research site, no login or API key
needed, so this stays inside the zero-spend rule. Needs `requests` (not in
requirements.txt, since nothing at runtime imports it) - install it ad hoc
before running this script.

Every ticker's *standalone* page is tried first (screener shows the full
Compounded Sales Growth ranges table, including the 10-Year figure, without
login for most standalone histories). Some tickers' standalone entity is
too young or too recently restructured to have a 10-year standalone series
(screener leaves the "10 Years:" cell blank rather than showing a wrong
number) - `--statement consolidated` falls back to that ticker's
consolidated page instead, exactly the standalone-vs-consolidated judgment
call Day 2's `research/sources.md` already had to make for Gulf Oil itself.

Usage:
    python scripts/fetch_peer_comparables.py --ticker CASTROLIND
    python scripts/fetch_peer_comparables.py --ticker GANDHAR --statement consolidated
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "fixtures" / "peers"
FIXTURE = OUT / "lubricants.csv"

RANGES_TABLES = ("Compounded Sales Growth", "Compounded Profit Growth", "Return on Equity")


def fetch_ranges(ticker: str, statement: str) -> dict[str, float | None]:
    """Scrape the free "ranges-table" boxes (sales/profit CAGR, ROE) plus price and market cap.

    These render server-side in plain HTML (unlike the P&L schedule table
    itself, which screener populates client-side and a plain ``requests``
    fetch never sees) - the same kind of load-bearing page-structure note
    `fetch_market_price.py` already makes about the ratios section.
    """
    path = "" if statement == "standalone" else f"{statement}/"
    url = f"https://www.screener.in/company/{ticker}/{path}"
    html = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"}).text

    def _number_after(label: str, span_class: str = "number", window: int = 500) -> float:
        idx = html.find(label)
        if idx == -1:
            raise SystemExit(f"{label!r} not found on {url} - page layout may have changed")
        match = re.search(rf'<span class="{span_class}">([\d,.]+)</span>', html[idx : idx + window])
        if match is None:
            raise SystemExit(f"no numeric value found after {label!r} on {url}")
        return float(match.group(1).replace(",", ""))

    def _ranges_row(table_label: str, row_label: str) -> float | None:
        # Each "ranges-table" is a small <table> of its own; scope the search
        # to the block starting at `table_label`'s own <th> so "10 Years:"
        # inside "Compounded Sales Growth" isn't confused with the same
        # label inside "Return on Equity" a few hundred bytes later.
        idx = html.find(table_label)
        if idx == -1:
            raise SystemExit(f"{table_label!r} ranges-table not found on {url}")
        block = html[idx : idx + 900]
        row_idx = block.find(row_label)
        if row_idx == -1:
            raise SystemExit(f"{row_label!r} row not found under {table_label!r} on {url}")
        match = re.search(r"<td>([\d.]*)%</td>", block[row_idx : row_idx + 120])
        if match is None or match.group(1) == "":
            return None  # screener leaves this blank when the underlying series is too short
        return float(match.group(1)) / 100

    return {
        "current_price": _number_after("Current Price"),
        "market_cap_cr": _number_after("Market Cap"),
        "sales_cagr_10y": _ranges_row("Compounded Sales Growth", "10 Years:"),
        "sales_cagr_5y": _ranges_row("Compounded Sales Growth", "5 Years:"),
        "profit_cagr_10y": _ranges_row("Compounded Profit Growth", "10 Years:"),
        "roe_10y": _ranges_row("Return on Equity", "10 Years:"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--name", required=True, help="display name for the comparison table")
    parser.add_argument("--statement", choices=["standalone", "consolidated"], default="standalone")
    args = parser.parse_args()

    fetched_date = pd.Timestamp.now().date().isoformat()
    ranges = fetch_ranges(args.ticker, args.statement)
    if ranges["sales_cagr_10y"] is None:
        raise SystemExit(
            f"{args.ticker}'s {args.statement} page has no 10-year Compounded Sales Growth figure - "
            "try --statement consolidated (or the other way round) before committing this row"
        )

    row = {
        "ticker": args.ticker,
        "name": args.name,
        "statement": args.statement,
        **ranges,
        "source_url": f"https://www.screener.in/company/{args.ticker}/"
        + ("" if args.statement == "standalone" else f"{args.statement}/"),
        "fetched_date": fetched_date,
    }

    OUT.mkdir(parents=True, exist_ok=True)
    if FIXTURE.exists():
        df = pd.read_csv(FIXTURE)
        df = df[df["ticker"] != args.ticker]
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    else:
        df = pd.DataFrame([row])
    df.to_csv(FIXTURE, index=False)
    print(f"{FIXTURE} updated: {args.ticker} ({args.statement}) - {ranges}")


if __name__ == "__main__":
    main()
