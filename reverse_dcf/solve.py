"""Reverse DCF solver (Day 5).

The forward engine (:mod:`reverse_dcf.forward`) takes growth as an input and
prices a share; this module inverts it. Given today's actual market price it
finds the constant explicit-period revenue growth rate that makes the
forward engine reproduce that price exactly, holding every other assumption
(margin, reinvestment, WACC, terminal growth) at Gulf Oil's own latest
fiscal-year actuals from :func:`reverse_dcf.forward.base_case_from_financials`.
That single number is the "implied CAGR" - what the market is already paying
for.

Two further outputs round this out, per ``NEXT_STEPS.md``'s Day 5 row:

- :func:`grid_implied_growth` reruns the same solve across every
  historically-realized combination of EBIT margin and reinvestment rate in
  ``data/GULFOILLUB/financials.csv`` (nine years of both, not an invented
  scenario set) - showing how sensitive the implied growth number is to
  which year's operating profile you assume continues.
- :func:`perpetual_breakeven_growth` answers a related but different
  question: instead of 10 explicit years followed by a slower terminal
  decay, what constant growth rate, held forever with no deceleration at
  all, would justify today's price? It reuses the exact
  forecast_years=1/terminal_growth=revenue_growth equivalence
  ``tests/test_forward.py`` already proves collapses the forward engine to
  the textbook single-stage Gordon growth formula - so it is not a new
  pricing method, only the existing one run with no explicit/terminal
  split. Because it never assumes the high-growth phase can end, it is
  always a lower (more conservative) number than the 10-year implied CAGR
  whenever growth is expected to decelerate.

Round-trip correctness (the repo's "Done when" gate): every solve here calls
:func:`scipy.optimize.brentq` on :func:`reverse_dcf.forward.run_dcf`'s own
``implied_share_price`` output, so a returned growth rate reproduces the
target price by construction, to ``xtol``. ``tests/test_solve.py`` checks
this explicitly rather than trusting the construction alone.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, replace
from pathlib import Path

import pandas as pd
from scipy.optimize import brentq

from reverse_dcf.financials import load_financials, to_numeric
from reverse_dcf.forward import (
    DEFAULT_FINANCIALS,
    base_case_from_financials,
    historical_reinvestment_rate,
    run_dcf,
)
from reverse_dcf.wacc import effective_tax_rate

ROOT = Path(__file__).resolve().parent.parent
MARKET_FIXTURES = ROOT / "fixtures" / "market"

GROWTH_BRACKET = (-0.99, 10.0)
"""Search range for the 10-year implied-growth solve. Wide enough that a real
root is always inside it if one exists (revenue can't shrink more than 99%/yr,
and no equity story needs >1000%/yr growth to justify a price) - the bracket's
job is only to bound the search, `run_dcf`'s own economics decide the root."""


@dataclass(frozen=True)
class MarketPrice:
    ticker: str
    price: float
    market_cap_cr: float
    date: str
    source_url: str


def load_market_price(ticker: str = "GULFOILLUB", fixtures_dir: str | Path = MARKET_FIXTURES) -> MarketPrice:
    """Load the committed market-price fixture for ``ticker``.

    Refresh it with ``scripts/fetch_market_price.py`` when a new price is
    needed; this loader only ever reads the committed CSV, so the solver
    never blocks on network access.
    """
    path = Path(fixtures_dir) / f"{ticker}.csv"
    df = pd.read_csv(path)
    row = df.iloc[-1]
    return MarketPrice(
        ticker=ticker,
        price=float(row["price"]),
        market_cap_cr=float(row["market_cap_cr"]),
        date=str(row["date"]),
        source_url=str(row["source_url"]),
    )


def _solve_growth(price_gap, bracket: tuple[float, float], label: str) -> float:
    lo, hi = bracket
    f_lo, f_hi = price_gap(lo), price_gap(hi)
    if f_lo * f_hi > 0:
        raise ValueError(
            f"no {label} found in growth bracket {bracket}: implied price at "
            f"{lo:.2%} growth is {f_lo:+.2f} away from target, at {hi:.2%} "
            f"growth is {f_hi:+.2f} away - both on the same side, so the "
            "target price is unreachable in this range at these assumptions"
        )
    return brentq(price_gap, lo, hi, xtol=1e-8)


def implied_growth(
    target_price: float,
    financials_path: str | Path = DEFAULT_FINANCIALS,
    *,
    forecast_years: int = 10,
    terminal_growth: float | None = None,
    ebit_margin: float | None = None,
    reinvestment_rate: float | None = None,
    wacc: float | None = None,
    bracket: tuple[float, float] = GROWTH_BRACKET,
) -> float:
    """Solve the explicit-period revenue growth that reproduces ``target_price``.

    Every other assumption comes from :func:`base_case_from_financials`
    (the latest fiscal year's actuals and Day 3's WACC) unless overridden -
    ``ebit_margin``/``reinvestment_rate`` overrides are what
    :func:`grid_implied_growth` sweeps, and ``wacc`` is what
    :mod:`reverse_dcf.sensitivity`'s tornado chart shocks alongside them.
    """
    base = base_case_from_financials(
        financials_path, revenue_growth=0.0, forecast_years=forecast_years, terminal_growth=terminal_growth
    )
    if ebit_margin is not None:
        base = replace(base, ebit_margin=ebit_margin)
    if reinvestment_rate is not None:
        base = replace(base, reinvestment_rate=reinvestment_rate)
    if wacc is not None:
        base = replace(base, wacc=wacc)

    def price_gap(g: float) -> float:
        return run_dcf(replace(base, revenue_growth=g)).implied_share_price - target_price

    return _solve_growth(price_gap, bracket, "implied growth")


def perpetual_breakeven_growth(
    target_price: float,
    financials_path: str | Path = DEFAULT_FINANCIALS,
    *,
    ebit_margin: float | None = None,
    reinvestment_rate: float | None = None,
) -> float:
    """The single constant growth rate, held forever, that reproduces ``target_price``.

    Runs the forward engine with ``forecast_years=1`` and
    ``terminal_growth == revenue_growth`` - the exact configuration
    ``tests/test_forward.py``'s
    ``test_enterprise_value_matches_a_growing_perpetuity_when_growth_equals_terminal_growth``
    proves collapses to the textbook one-stage Gordon growth value. Unlike
    :func:`implied_growth`, this growth rate is never allowed to decelerate
    to a slower terminal rate after year 10, so it is a lower, more
    conservative bar: a business priced for 10 years of fast growth then a
    slowdown needs a *higher* 10-year number than it would need if that pace
    literally never ended.
    """
    base = base_case_from_financials(financials_path, revenue_growth=0.0, forecast_years=1, terminal_growth=0.0)
    if ebit_margin is not None:
        base = replace(base, ebit_margin=ebit_margin)
    if reinvestment_rate is not None:
        base = replace(base, reinvestment_rate=reinvestment_rate)
    wacc = base.wacc

    def price_gap(g: float) -> float:
        return run_dcf(replace(base, revenue_growth=g, terminal_growth=g)).implied_share_price - target_price

    bracket = (-0.99, wacc - 1e-6)
    return _solve_growth(price_gap, bracket, "perpetual breakeven growth")


def historical_margins_and_reinvestment(
    financials_path: str | Path = DEFAULT_FINANCIALS,
) -> tuple[dict[str, float], dict[str, float]]:
    """EBIT margin (all years) and reinvestment rate (years 2..N) actually realized, by fiscal year.

    Used as :func:`grid_implied_growth`'s sweep axes so the sensitivity grid
    is grounded in Gulf Oil's own ten-year range rather than an invented
    scenario set.
    """
    df = to_numeric(load_financials(financials_path)).set_index("fiscal_year")
    years = list(df.index)
    tax_rates = {y: effective_tax_rate(df.loc[y, "ebit"], df.loc[y, "interest_expense"], df.loc[y, "tax_expense"]) for y in years}
    margins = {y: df.loc[y, "ebit"] / df.loc[y, "revenue"] for y in years}
    reinvestment = {
        y: historical_reinvestment_rate(df.loc[y], df.loc[py], tax_rates[y]) for py, y in zip(years, years[1:])
    }
    return margins, reinvestment


def grid_implied_growth(
    target_price: float,
    financials_path: str | Path = DEFAULT_FINANCIALS,
    *,
    margins: list[float],
    reinvestment_rates: list[float],
    forecast_years: int = 10,
    terminal_growth: float | None = None,
    bracket: tuple[float, float] = GROWTH_BRACKET,
) -> pd.DataFrame:
    """Implied growth for every (margin, reinvestment_rate) combination, as a margin x reinvestment grid.

    A cell is ``NaN`` where no root exists in ``bracket`` at that
    combination (e.g. a reinvestment rate above 100% flips the sign of
    FCFF, and an extreme-enough margin/reinvestment pairing can put the
    target price out of reach) - a hole in the grid, not a solver bug.
    """
    rows = []
    for margin in margins:
        row = {}
        for reinvestment_rate in reinvestment_rates:
            try:
                row[reinvestment_rate] = implied_growth(
                    target_price,
                    financials_path,
                    forecast_years=forecast_years,
                    terminal_growth=terminal_growth,
                    ebit_margin=margin,
                    reinvestment_rate=reinvestment_rate,
                    bracket=bracket,
                )
            except ValueError:
                row[reinvestment_rate] = float("nan")
        rows.append(row)
    grid = pd.DataFrame(rows, index=margins)
    grid.index.name = "ebit_margin"
    grid.columns.name = "reinvestment_rate"
    return grid


@dataclass(frozen=True)
class ReverseDcfResult:
    ticker: str
    target_price: float
    implied_growth: float
    ebit_margin: float
    reinvestment_rate: float
    wacc: float
    terminal_growth: float
    breakeven_growth: float
    forecast_years: int

    def summary(self) -> str:
        lines = [
            f"Reverse DCF -- {self.ticker} at Rs{self.target_price:,.2f}/share",
            f"  Forecast horizon:                    {self.forecast_years} years",
            f"  EBIT margin (latest FY, held fixed): {self.ebit_margin:.2%}",
            f"  Reinvestment rate (latest FY, fixed):{self.reinvestment_rate:.2%}",
            f"  WACC:                                {self.wacc:.2%}",
            f"  Terminal growth:                     {self.terminal_growth:.2%}",
            f"  Implied revenue growth (10y CAGR):    {self.implied_growth:.2%}",
            f"  Perpetual breakeven growth:           {self.breakeven_growth:.2%}",
        ]
        return "\n".join(lines) + "\n"

    def to_contract(self) -> dict:
        """The ``valuation`` block this repo publishes to the spine (v0.7)."""
        return {
            "valuation": {
                "implied_cagr": self.implied_growth,
                "implied_ebit_margin": self.ebit_margin,
                "implied_reinvestment": self.reinvestment_rate,
                "breakeven_growth": self.breakeven_growth,
            }
        }


def solve(
    target_price: float,
    financials_path: str | Path = DEFAULT_FINANCIALS,
    *,
    ticker: str = "GULFOILLUB",
    forecast_years: int = 10,
    terminal_growth: float | None = None,
) -> ReverseDcfResult:
    """Run the full Day 5 reverse solve: implied growth plus the perpetual breakeven, at the base-case margin/reinvestment."""
    base = base_case_from_financials(
        financials_path, revenue_growth=0.0, forecast_years=forecast_years, terminal_growth=terminal_growth
    )
    g = implied_growth(target_price, financials_path, forecast_years=forecast_years, terminal_growth=base.terminal_growth)
    breakeven = perpetual_breakeven_growth(target_price, financials_path)
    return ReverseDcfResult(
        ticker=ticker,
        target_price=target_price,
        implied_growth=g,
        ebit_margin=base.ebit_margin,
        reinvestment_rate=base.reinvestment_rate,
        wacc=base.wacc,
        terminal_growth=base.terminal_growth,
        breakeven_growth=breakeven,
        forecast_years=forecast_years,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="GULFOILLUB")
    parser.add_argument("--financials", default=str(DEFAULT_FINANCIALS))
    parser.add_argument("--price", type=float, default=None, help="current market price; defaults to fixtures/market/<ticker>.csv")
    parser.add_argument("--years", type=int, default=10, help="explicit forecast horizon in years")
    parser.add_argument(
        "--terminal-growth",
        type=float,
        default=None,
        help="defaults to the current India risk-free rate, same as reverse_dcf.forward",
    )
    parser.add_argument(
        "--grid",
        action="store_true",
        help="also print the implied-growth grid over Gulf Oil's own ten-year margin/reinvestment history",
    )
    parser.add_argument(
        "--contract",
        metavar="PATH",
        default=None,
        help="write the v0.7 valuation contract block (see to_contract()) as JSON to this path, "
        "for the spine to read as a file -- never as a Python import",
    )
    args = parser.parse_args()

    market = None
    if args.price is None:
        market = load_market_price(args.ticker)
        price = market.price
    else:
        price = args.price

    result = solve(price, args.financials, ticker=args.ticker, forecast_years=args.years, terminal_growth=args.terminal_growth)
    print(result.summary())
    if market is not None:
        print(f"(price Rs{market.price:,.2f} from {market.source_url}, as of {market.date})")

    if args.contract:
        contract_path = Path(args.contract)
        contract_path.parent.mkdir(parents=True, exist_ok=True)
        contract_path.write_text(json.dumps(result.to_contract(), indent=2) + "\n")
        print(f"\nwrote valuation contract to {contract_path}")

    if args.grid:
        margins, reinvestment = historical_margins_and_reinvestment(args.financials)
        grid = grid_implied_growth(
            price,
            args.financials,
            margins=sorted(set(margins.values())),
            reinvestment_rates=sorted(set(reinvestment.values())),
            forecast_years=args.years,
            terminal_growth=result.terminal_growth,
        )
        print("\nImplied growth by (EBIT margin x reinvestment rate), swept over Gulf Oil's own 10-year history:")
        print(grid.map(lambda x: f"{x:.1%}" if pd.notna(x) else "n/a").to_string())


if __name__ == "__main__":
    main()
