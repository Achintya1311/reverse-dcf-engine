"""Set the implied figures against history and peers (Day 6).

Day 5 answered "what growth does today's price already assume?" in
isolation. That number means nothing on its own - a market-implied 10-year
CAGR of, say, -0.5% is only a finding once it sits next to something real:
what Gulf Oil itself has actually grown at over the ten years already on
record (:func:`historical_revenue_cagr`, computed directly from
``data/GULFOILLUB/financials.csv``, the same source Day 2 hand-transcribed
and cited), and what comparable lubricant/oil companies have grown at over
a similar window (:func:`load_peer_comparables`, sourced from screener.in's
free "Compounded Sales Growth" ranges tables via
``scripts/fetch_peer_comparables.py``).

:func:`comparison_table` is the actual Day 6 deliverable per
``NEXT_STEPS.md``: one table, one growth-rate column, every row directly
comparable to every other row, so the write-up this project exists to
produce can point at it rather than assert a conclusion.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from reverse_dcf.financials import load_financials, to_numeric
from reverse_dcf.forward import DEFAULT_FINANCIALS
from reverse_dcf.solve import load_market_price, solve

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PEERS = ROOT / "fixtures" / "peers" / "lubricants.csv"


def historical_revenue_cagr(financials_path: str | Path = DEFAULT_FINANCIALS, *, skip_years: int = 0) -> float:
    """Gulf Oil's own realized revenue CAGR across every fiscal year in ``financials_path``.

    ``(last year's revenue / first year's revenue) ** (1 / (N-1)) - 1`` over
    the ``N`` fiscal years on record - the same figure the README has
    quoted since Day 2, now computed rather than eyeballed, so it can be
    asserted against in a test instead of re-typed by hand each time a
    fiscal year is added.

    ``skip_years`` drops that many earliest fiscal years before computing -
    added for Day 9's grilling pass (:mod:`reverse_dcf.grill`), which uses
    ``skip_years=1`` to recompute this CAGR with FY2014-15 (the flagged
    restructuring year, see the README's own limitations entry) dropped as
    the base year, to check whether that flagged year is propping up the
    headline realized-growth number.
    """
    df = to_numeric(load_financials(financials_path)).set_index("fiscal_year")
    years = list(df.index)[skip_years:]
    if len(years) < 2:
        raise ValueError("need at least two fiscal years to compute a CAGR")
    first, last = df.loc[years[0], "revenue"], df.loc[years[-1], "revenue"]
    periods = len(years) - 1
    return (last / first) ** (1 / periods) - 1


def load_peer_comparables(peers_path: str | Path = DEFAULT_PEERS) -> pd.DataFrame:
    """Load the committed peer-comparables fixture.

    Refresh it with ``scripts/fetch_peer_comparables.py``; this loader only
    ever reads the committed CSV, so the comparison never blocks on network
    access, same discipline as :func:`reverse_dcf.solve.load_market_price`.
    """
    return pd.read_csv(peers_path)


def comparison_table(
    target_price: float,
    financials_path: str | Path = DEFAULT_FINANCIALS,
    peers_path: str | Path = DEFAULT_PEERS,
    *,
    ticker: str = "GULFOILLUB",
) -> pd.DataFrame:
    """The Day 6 deliverable: implied growth, this company's own history, and its peers, one column.

    Every row reports a revenue growth rate on the same basis (a CAGR, not
    a single-year number) so they can be read straight down the column.
    ``kind`` distinguishes what the market is assumed to be pricing in
    (``implied``) from what has actually happened (``realized``) - the
    distinction this whole project is built to make legible.
    """
    result = solve(target_price, financials_path, ticker=ticker)
    own_realized = historical_revenue_cagr(financials_path)

    rows = [
        {
            "entity": ticker,
            "kind": "implied - 10yr (Day 5)",
            "revenue_cagr": result.implied_growth,
            "note": f"market-implied at Rs{target_price:,.2f}/share",
        },
        {
            "entity": ticker,
            "kind": "implied - perpetual breakeven (Day 5)",
            "revenue_cagr": result.breakeven_growth,
            "note": "same price, growth held forever, no deceleration",
        },
        {
            "entity": ticker,
            "kind": "realized - 10yr history (own financials)",
            "revenue_cagr": own_realized,
            "note": "data/GULFOILLUB/financials.csv, FY2014-15 to FY2023-24",
        },
    ]

    peers = load_peer_comparables(peers_path)
    for _, peer in peers.iterrows():
        if peer["ticker"] == ticker:
            continue  # the fixture also carries GULFOILLUB itself, as a cross-check row below, not a peer
        rows.append(
            {
                "entity": f"{peer['name']} ({peer['ticker']})",
                "kind": f"realized - 10yr history (peer, {peer['statement']})",
                "revenue_cagr": peer["sales_cagr_10y"],
                "note": f"screener.in, {peer['fetched_date']}",
            }
        )

    own_screener_row = peers[peers["ticker"] == ticker]
    if not own_screener_row.empty:
        rows.append(
            {
                "entity": ticker,
                "kind": "realized - 10yr history (screener.in cross-check)",
                "revenue_cagr": float(own_screener_row.iloc[0]["sales_cagr_10y"]),
                "note": "independent source, own-financials row above is the one this project cites",
            }
        )

    table = pd.DataFrame(rows, columns=["entity", "kind", "revenue_cagr", "note"])
    return table


def format_table(table: pd.DataFrame) -> str:
    printable = table.copy()
    printable["revenue_cagr"] = printable["revenue_cagr"].map(lambda x: f"{x:.2%}")
    return printable.to_string(index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="GULFOILLUB")
    parser.add_argument("--financials", default=str(DEFAULT_FINANCIALS))
    parser.add_argument("--peers", default=str(DEFAULT_PEERS))
    parser.add_argument("--price", type=float, default=None, help="current market price; defaults to fixtures/market/<ticker>.csv")
    args = parser.parse_args()

    if args.price is None:
        price = load_market_price(args.ticker).price
    else:
        price = args.price

    table = comparison_table(price, args.financials, args.peers, ticker=args.ticker)
    print(f"Implied growth vs. history vs. peers -- {args.ticker} at Rs{price:,.2f}/share\n")
    print(format_table(table))


if __name__ == "__main__":
    main()
