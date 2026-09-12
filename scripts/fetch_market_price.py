"""Rebuild fixtures/market/<TICKER>.csv from screener.in (Day 5).

Not part of the solver's runtime path - `reverse_dcf.solve` only reads the
committed CSV fixture, so tests and `python -m reverse_dcf.solve` never need
network access. This script exists so the market-price input is
reproducible rather than a one-off hand-copy: re-run it to refresh the
current price before a fresh reverse solve.

screener.in is a free public equity-research site, no login or API key
needed, so this stays inside the zero-spend rule. Needs `requests` (not in
requirements.txt, since nothing at runtime imports it) - install it ad hoc
(`pip install requests`) before running this script.

Usage:
    python scripts/fetch_market_price.py --ticker GULFOILLUB
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "fixtures" / "market"


def fetch_price(ticker: str) -> tuple[float, float]:
    """Return ``(price, market_cap_cr)`` scraped off screener.in's consolidated page.

    screener.in renders both figures as ``<span class="number">`` right
    after a ``<span class="name">Market Cap</span>`` / ``Current Price``
    label, in that order, with no other stable attribute to key off (same
    situation ``fetch_wacc_inputs.py`` found on Damodaran's ctryprem page).
    """
    url = f"https://www.screener.in/company/{ticker}/consolidated/"
    html = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"}).text

    def _number_after(label: str) -> float:
        # The ratios section renders `<span class="name">\n  Market Cap\n</span>`
        # (whitespace-wrapped, no attribute tying name to value) followed by a
        # `<span class="number">` a few lines later - so this locates the label
        # text itself, then the next number span after it, rather than matching
        # an exact ">label<" substring that the surrounding whitespace breaks.
        idx = html.find(label)
        if idx == -1:
            raise SystemExit(f"{label!r} not found on {url} - page layout may have changed")
        match = re.search(r'<span class="number">([\d,.]+)</span>', html[idx : idx + 500])
        if match is None:
            raise SystemExit(f"no numeric value found after {label!r} on {url}")
        return float(match.group(1).replace(",", ""))

    return _number_after("Current Price"), _number_after("Market Cap")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="GULFOILLUB")
    args = parser.parse_args()

    fetched_date = pd.Timestamp.now().date().isoformat()
    price, market_cap_cr = fetch_price(args.ticker)

    out_path = OUT / f"{args.ticker}.csv"
    pd.DataFrame(
        [
            {
                "date": fetched_date,
                "price": price,
                "market_cap_cr": market_cap_cr,
                "source_url": f"https://www.screener.in/company/{args.ticker}/consolidated/",
                "fetched_date": fetched_date,
            }
        ]
    ).to_csv(out_path, index=False)
    print(f"{out_path} refreshed: price=Rs{price:,.2f}, market_cap=Rs{market_cap_cr:,.0f} cr ({fetched_date})")


if __name__ == "__main__":
    main()
