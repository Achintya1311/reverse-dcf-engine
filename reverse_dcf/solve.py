"""Reverse DCF solver (Day 5).

The forward engine (:mod:`reverse_dcf.forward`) takes growth as an input and
prices a share; this module inverts it. Given today's actual market price it
finds the constant explicit-period revenue growth rate that makes the
forward engine reproduce that price exactly, holding margin, WACC and
terminal growth at Gulf Oil's own latest fiscal-year actuals from
:func:`reverse_dcf.forward.base_case_from_financials`. That single number is
the "implied CAGR" - what the market is already paying for.

V2 (CRITIQUES.md V1): reinvestment is no longer in that "held fixed" list.
V1 pinned it to one historical fiscal year's actual rate regardless of the
growth being solved for, which could (and for Gulf Oil's own base case,
did) pair a positive growth rate with a negative reinvestment rate - no
real return on capital makes that combination possible. V2 instead
re-derives reinvestment from whatever growth the root-finder is trying,
via the fundamental growth identity and a ROIC that fades from the
business's own historical median toward its cost of capital -- see
:func:`reverse_dcf.forward.roic_fade_schedule` and
:func:`reverse_dcf.forward.reinvestment_schedule_from_growth`.

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
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import pandas as pd
from scipy.optimize import brentq, minimize_scalar

from reverse_dcf.financials import load_financials, to_numeric
from reverse_dcf.live_financials import FINANCIALS_SOURCE_HAND, FINANCIALS_SOURCE_LIVE, write_live_financials_csv
from reverse_dcf.forward import (
    DEFAULT_FINANCIALS,
    TERMINAL_ROIC_SPREAD_DEFAULT,
    base_case_from_financials,
    historical_median_roic,
    historical_reinvestment_rate,
    historical_roic_by_year,
    is_working_capital_release_year,
    reinvestment_schedule_from_growth,
    roic_fade_schedule,
    run_dcf,
    terminal_roic,
)
from reverse_dcf.wacc import effective_tax_rate

ROOT = Path(__file__).resolve().parent.parent
MARKET_FIXTURES = ROOT / "fixtures" / "market"

GROWTH_BRACKET = (-0.99, 10.0)
"""Search range for the 10-year implied-growth solve. Wide enough that a real
root is always inside it if one exists (revenue can't shrink more than 99%/yr,
and no equity story needs >1000%/yr growth to justify a price) - the bracket's
job is only to bound the search, `run_dcf`'s own economics decide the root.

V2: when :func:`implied_growth` isn't given an explicit ``reinvestment_rate``
override, this default upper end is clamped down to just below the
growth/ROIC schedule's own lowest ROIC year (see that function and
:func:`reverse_dcf.forward.roic_fade_schedule`) - past that point
reinvestment exceeds 100% of NOPAT for at least one explicit year, which
:func:`_solve_growth` can still search through (nothing raises), but which
is no longer the ordinary growing-business case this bracket's width was
originally sized for."""


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


class PriceUnreachableError(ValueError):
    """No growth rate anywhere in the search bracket reproduces the target price.

    Raised instead of the generic same-sign-at-both-ends message when
    :func:`_solve_growth` has actually checked the bracket's own interior
    extremum (not just its two endpoints) and confirmed there is no root at
    all -- see that function's V2 docstring note. ``best_growth`` and
    ``best_price_gap`` (``price(best_growth) - target_price``) are the
    closest this bracket can get, so a caller can report *how* unreachable
    the target is, not just that it is.
    """

    def __init__(self, message: str, best_growth: float, best_price_gap: float) -> None:
        super().__init__(message)
        self.best_growth = best_growth
        self.best_price_gap = best_price_gap


def _solve_growth(price_gap, bracket: tuple[float, float], label: str) -> float:
    """Find the growth rate in ``bracket`` where ``price_gap`` (price at that growth minus
    the target) crosses zero.

    V1's fixed reinvestment rate made price strictly increasing in growth,
    so same-sign endpoints always meant "the root is somewhere outside this
    bracket." V2's reinvestment grows with the growth rate itself
    (:func:`reverse_dcf.forward.reinvestment_schedule_from_growth`), so
    price can rise then fall (or the reverse) *inside* the bracket - two
    roots, one, or none, independent of what the two endpoints alone show.
    Same-sign endpoints here first check the bracket's own interior
    extremum before concluding there is no root, and if a root exists
    between one endpoint and that extremum, solves on that half.
    """
    lo, hi = bracket
    f_lo, f_hi = price_gap(lo), price_gap(hi)
    if f_lo * f_hi <= 0:
        return brentq(price_gap, lo, hi, xtol=1e-8)

    if f_lo > 0:  # price stays above target at both ends -- look for a dip below it
        probe = minimize_scalar(price_gap, bounds=bracket, method="bounded")
        extreme_gap, extreme_g = probe.fun, probe.x
    else:  # price stays below target at both ends -- look for a rise above it
        probe = minimize_scalar(lambda g: -price_gap(g), bounds=bracket, method="bounded")
        extreme_gap, extreme_g = -probe.fun, probe.x

    if extreme_gap * f_lo > 0:
        # same sign as the endpoints too: price never reaches the target anywhere in bracket.
        raise PriceUnreachableError(
            f"no {label} found anywhere in growth bracket {bracket}, not just outside it: "
            f"implied price is {f_lo:+.2f} away from target at {lo:.2%} growth, {f_hi:+.2f} "
            f"away at {hi:.2%}, and this bracket's own best case (growth {extreme_g:+.2%}) is "
            f"still {extreme_gap:+.2f} away - the target price is unreachable at these assumptions",
            best_growth=extreme_g,
            best_price_gap=extreme_gap,
        )
    if f_lo * extreme_gap <= 0:
        return brentq(price_gap, lo, extreme_g, xtol=1e-8)
    return brentq(price_gap, extreme_g, hi, xtol=1e-8)


def implied_growth(
    target_price: float,
    financials_path: str | Path = DEFAULT_FINANCIALS,
    *,
    forecast_years: int = 10,
    terminal_growth: float | None = None,
    ebit_margin: float | None = None,
    reinvestment_rate: float | None = None,
    wacc: float | None = None,
    roic_spread: float = TERMINAL_ROIC_SPREAD_DEFAULT,
    bracket: tuple[float, float] = GROWTH_BRACKET,
    ticker: str | None = None,
) -> float:
    """Solve the explicit-period revenue growth that reproduces ``target_price``.

    Every other assumption comes from :func:`base_case_from_financials`
    (the latest fiscal year's actuals and Day 3's WACC) unless overridden -
    ``ebit_margin`` is what :func:`grid_implied_growth` sweeps alongside
    ``reinvestment_rate``, and ``wacc`` is what
    :mod:`reverse_dcf.sensitivity`'s tornado chart shocks alongside both.

    V2: when ``reinvestment_rate`` is *not* given, reinvestment is not a
    fixed historical number either -- it is re-derived for every growth rate
    the root-finder tries, via :func:`reverse_dcf.forward.roic_fade_schedule`
    and :func:`reverse_dcf.forward.reinvestment_schedule_from_growth`, the
    same way :func:`base_case_from_financials` now does by default
    (CRITIQUES.md V1). Passing an explicit ``reinvestment_rate`` bypasses
    that and goes back to a flat rate for every year, same as V1 - the
    escape hatch :func:`grid_implied_growth` and
    :mod:`reverse_dcf.sensitivity`'s reinvestment-rate shock both still use
    deliberately, since they are testing "what if this flat historical rate
    persisted" rather than the growth-consistent model.
    """
    base = base_case_from_financials(
        financials_path,
        revenue_growth=0.0,
        forecast_years=forecast_years,
        terminal_growth=terminal_growth,
        wacc=wacc,
        roic_spread=roic_spread,
        ticker=ticker,
    )
    if ebit_margin is not None:
        base = replace(base, ebit_margin=ebit_margin)

    if reinvestment_rate is not None:
        # A flat override is meant to hold forever (V1-style), so the
        # terminal year reinvests at that same flat rate too -- reset the
        # V2 schedule's terminal_growth/terminal_roic figure base_case_from_financials
        # computed for the *unoverridden* schedule (CRITIQUES.md V6).
        base = replace(base, reinvestment_rate=reinvestment_rate, terminal_reinvestment_rate=None)

        def price_gap(g: float) -> float:
            return run_dcf(replace(base, revenue_growth=g)).implied_share_price - target_price
    else:
        median_roic = historical_median_roic(financials_path, ticker=ticker)
        roic_schedule = roic_fade_schedule(
            median_roic, terminal_roic(base.wacc, roic_spread), forecast_years, ticker=ticker
        )
        if bracket is GROWTH_BRACKET:
            # V2: unlike V1's fixed reinvestment rate, reinvestment = g / roic
            # grows without bound as g rises, passing 100% once g exceeds the
            # schedule's lowest ROIC year - past that, FCFF for that year (and,
            # soon after, the whole explicit period) goes negative, and implied
            # price stops being monotonic in g. GROWTH_BRACKET's wide default
            # upper end (1000%/yr, sized for V1's always-monotonic pricing) can
            # straddle more than one root there, so when the caller leaves the
            # default bracket alone, clamp its upper end below the schedule's
            # own floor - the same "growth can't exceed the ROIC available to
            # fund it" bound perpetual_breakeven_growth already enforces against
            # wacc for the one-year case.
            bracket = (bracket[0], min(roic_schedule) - 1e-6)

        def price_gap(g: float) -> float:
            schedule = reinvestment_schedule_from_growth(g, roic_schedule)
            return run_dcf(replace(base, revenue_growth=g, reinvestment_rate=schedule)).implied_share_price - target_price

    return _solve_growth(price_gap, bracket, "implied growth")


def perpetual_breakeven_growth(
    target_price: float,
    financials_path: str | Path = DEFAULT_FINANCIALS,
    *,
    ebit_margin: float | None = None,
    reinvestment_rate: float | None = None,
    roic_spread: float = TERMINAL_ROIC_SPREAD_DEFAULT,
    ticker: str | None = None,
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

    V2: with no ``reinvestment_rate`` override, reinvestment is
    ``revenue_growth / terminal_roic`` -- :func:`reverse_dcf.forward.roic_fade_schedule`
    with ``forecast_years=1`` always resolves to the terminal ROIC anchor,
    on the reasoning that one explicit year immediately followed by the
    same rate forever *is* the terminal state, not a fading-from-median
    window (there is no "from" with only one year).

    V6 (CRITIQUES.md, Day 18): unlike :func:`reverse_dcf.forward.base_case_from_financials`'s
    ordinary ``terminal_growth``, the growth rate this function searches for
    is *not* capped at the risk-free rate. That cap exists so a realistic
    terminal deceleration target never outpaces the economy forever; this
    function instead asks the deliberately more aggressive hypothetical
    "what if the explicit pace itself never decelerated at all" (see above),
    so its own bracket stays bounded only by ``wacc`` (the ordinary
    perpetuity-validity requirement), the same as before Day 18.
    """
    base = base_case_from_financials(
        financials_path,
        revenue_growth=0.0,
        forecast_years=1,
        terminal_growth=0.0,
        roic_spread=roic_spread,
        ticker=ticker,
    )
    if ebit_margin is not None:
        base = replace(base, ebit_margin=ebit_margin)
    wacc = base.wacc

    if reinvestment_rate is not None:
        base = replace(base, reinvestment_rate=reinvestment_rate)

        def price_gap(g: float) -> float:
            # terminal_reinvestment_rate=None: base_case_from_financials's
            # placeholder call above (terminal_growth=0.0) baked in a stale
            # figure; resetting it here falls back to this same flat
            # reinvestment_rate for the terminal year too, matching
            # "one growth rate, held forever, with one flat reinvestment
            # rate" -- this function's whole premise (CRITIQUES.md V6).
            return run_dcf(
                replace(base, revenue_growth=g, terminal_growth=g, terminal_reinvestment_rate=None)
            ).implied_share_price - target_price
    else:
        terminal_roic_value = terminal_roic(wacc, roic_spread)

        def price_gap(g: float) -> float:
            schedule = [g / terminal_roic_value]
            # Same reset as above: forecast_years=1 means the explicit year
            # *is* the terminal year (roic_fade_schedule's own docstring),
            # so the terminal rate must track g via this schedule, not the
            # stale placeholder from the initial base_case_from_financials call.
            return run_dcf(
                replace(
                    base,
                    revenue_growth=g,
                    terminal_growth=g,
                    reinvestment_rate=schedule,
                    terminal_reinvestment_rate=None,
                )
            ).implied_share_price - target_price

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


def working_capital_release_years(financials_path: str | Path = DEFAULT_FINANCIALS) -> list[str]:
    """Fiscal years (2..N) where net working capital fell versus the prior year.

    See :func:`reverse_dcf.forward.is_working_capital_release_year`. These
    are the years a reinvestment rate reads artificially low (or negative)
    for a reason that has nothing to do with the business shrinking its
    capital base.
    """
    df = to_numeric(load_financials(financials_path)).set_index("fiscal_year")
    years = list(df.index)
    return [y for py, y in zip(years, years[1:]) if is_working_capital_release_year(df.loc[y], df.loc[py])]


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
    implied_growth: float | None
    """``None`` when no growth rate reproduces ``target_price`` under V2's
    model -- see ``price_reachable`` and ``max_achievable_price_10y``."""
    ebit_margin: float
    median_roic: float
    terminal_roic: float
    implied_reinvestment_year1: float | None
    implied_reinvestment_terminal: float | None
    wacc: float
    terminal_growth: float
    breakeven_growth: float | None
    """``None`` when no perpetual growth rate reproduces ``target_price`` --
    see ``breakeven_reachable`` and ``max_achievable_price_perpetual``."""
    forecast_years: int
    price_reachable: bool
    max_achievable_price_10y: float
    growth_at_max_achievable_price_10y: float
    breakeven_reachable: bool
    max_achievable_price_perpetual: float
    growth_at_max_achievable_price_perpetual: float
    financials_source: str = FINANCIALS_SOURCE_HAND
    """C1 Day 23: which financials this result was solved against --
    :data:`reverse_dcf.live_financials.FINANCIALS_SOURCE_HAND` (GULFOILLUB's
    own ten-year, hand-transcribed base case, the default for every call
    before Day 23) or :data:`...FINANCIALS_SOURCE_LIVE` (any ticker, via the
    yfinance adapter). Carried through :meth:`to_contract` as an additive
    key so nothing downstream mistakes a "lite" live result for the
    hand-verified GULFOILLUB one."""

    def summary(self) -> str:
        lines = [
            f"Reverse DCF -- {self.ticker} at Rs{self.target_price:,.2f}/share",
            f"  Forecast horizon:                    {self.forecast_years} years",
            f"  EBIT margin (latest FY, held fixed): {self.ebit_margin:.2%}",
            f"  Historical median ROIC (V2 anchor):  {self.median_roic:.2%}",
            f"  Terminal ROIC (WACC + stated spread):{self.terminal_roic:.2%}",
        ]
        if self.price_reachable:
            lines += [
                f"  Implied reinvestment, year 1:        {self.implied_reinvestment_year1:.2%}",
                f"  Implied reinvestment, year {self.forecast_years}:       {self.implied_reinvestment_terminal:.2%}",
                f"  WACC:                                {self.wacc:.2%}",
                f"  Terminal growth:                     {self.terminal_growth:.2%}",
                f"  Implied revenue growth (10y CAGR):    {self.implied_growth:.2%}",
            ]
        else:
            lines += [
                f"  WACC:                                {self.wacc:.2%}",
                f"  Terminal growth:                     {self.terminal_growth:.2%}",
                "  Implied revenue growth (10y CAGR):    none -- no constant growth rate reproduces this price",
                f"    (V2's ceiling: Rs{self.max_achievable_price_10y:,.2f}/share at "
                f"{self.growth_at_max_achievable_price_10y:+.2%} growth, still short of the target)",
            ]
        if self.breakeven_reachable:
            lines.append(f"  Perpetual breakeven growth:           {self.breakeven_growth:.2%}")
        else:
            lines.append(
                "  Perpetual breakeven growth:           none -- ceiling is "
                f"Rs{self.max_achievable_price_perpetual:,.2f}/share at "
                f"{self.growth_at_max_achievable_price_perpetual:+.2%} growth"
            )
        return "\n".join(lines) + "\n"

    def to_contract(self) -> dict:
        """The ``valuation`` block this repo publishes to the spine (v0.7, V2 keys added).

        ``implied_cagr``, ``implied_ebit_margin``, ``implied_reinvestment``
        and ``breakeven_growth`` are the original v0.7 keys, kept as-is
        (``implied_reinvestment`` now means the *year 1* rate of V2's
        schedule, not V1's single flat rate, but the key's shape --
        one float, or ``null`` when unreachable -- is unchanged, so
        STOCKSTALKER's gate, which only requires these four keys to be
        present, reads it the same way it always has).
        ``implied_reinvestment_terminal``, ``median_roic``, ``terminal_roic``,
        ``price_reachable`` and the two ``max_achievable_price*``/
        ``growth_at_max_achievable_price*`` pairs are new, additive keys --
        same "new keys only, keep the shape" convention NEXT_STEPS.md's
        Day 6 risk-contract row uses.
        """
        return {
            "valuation": {
                "implied_cagr": self.implied_growth,
                "implied_ebit_margin": self.ebit_margin,
                "implied_reinvestment": self.implied_reinvestment_year1,
                "breakeven_growth": self.breakeven_growth,
                "implied_reinvestment_terminal": self.implied_reinvestment_terminal,
                "median_roic": self.median_roic,
                "terminal_roic": self.terminal_roic,
                "price_reachable": self.price_reachable,
                "max_achievable_price_10y": self.max_achievable_price_10y,
                "growth_at_max_achievable_price_10y": self.growth_at_max_achievable_price_10y,
                "breakeven_reachable": self.breakeven_reachable,
                "max_achievable_price_perpetual": self.max_achievable_price_perpetual,
                "growth_at_max_achievable_price_perpetual": self.growth_at_max_achievable_price_perpetual,
                "financials_source": self.financials_source,
            }
        }


def solve(
    target_price: float,
    financials_path: str | Path = DEFAULT_FINANCIALS,
    *,
    ticker: str = "GULFOILLUB",
    forecast_years: int = 10,
    terminal_growth: float | None = None,
    roic_spread: float = TERMINAL_ROIC_SPREAD_DEFAULT,
    financials_source: str = FINANCIALS_SOURCE_HAND,
) -> ReverseDcfResult:
    """Run the full Day 5 reverse solve: implied growth plus the perpetual breakeven, at the base-case margin and V2's growth/ROIC-derived reinvestment schedule.

    V2 (CRITIQUES.md V1): fixing the growth/reinvestment identity means
    price is no longer guaranteed to rise without limit as growth rises --
    see :func:`reverse_dcf.forward.roic_fade_schedule`. For GULFOILLUB at
    today's committed price, neither the 10-year nor the perpetual model
    can actually reach it: both raise :class:`PriceUnreachableError`, caught
    here rather than left to crash the CLI, and reported as
    ``price_reachable=False``/``breakeven_reachable=False`` plus the
    ceiling each model tops out at. That is itself the headline V2 result,
    not a bug to engineer around (PLAN.md rule 5: honest results, including
    when a fix makes a number worse).
    """
    base = base_case_from_financials(
        financials_path,
        revenue_growth=0.0,
        forecast_years=forecast_years,
        terminal_growth=terminal_growth,
        roic_spread=roic_spread,
        ticker=ticker,
    )
    median_roic = historical_median_roic(financials_path, ticker=ticker)
    terminal_roic_value = terminal_roic(base.wacc, roic_spread)
    roic_schedule = roic_fade_schedule(median_roic, terminal_roic_value, forecast_years, ticker=ticker)

    try:
        g = implied_growth(
            target_price,
            financials_path,
            forecast_years=forecast_years,
            terminal_growth=base.terminal_growth,
            roic_spread=roic_spread,
            ticker=ticker,
        )
        price_reachable = True
        reinvestment_schedule = reinvestment_schedule_from_growth(g, roic_schedule)
        max_price_10y, growth_at_max_10y = target_price, g
        implied_reinvestment_year1, implied_reinvestment_terminal = (
            reinvestment_schedule[0],
            reinvestment_schedule[-1],
        )
    except PriceUnreachableError as exc:
        g = None
        price_reachable = False
        max_price_10y = target_price + exc.best_price_gap
        growth_at_max_10y = exc.best_growth
        implied_reinvestment_year1 = implied_reinvestment_terminal = None

    try:
        breakeven = perpetual_breakeven_growth(target_price, financials_path, roic_spread=roic_spread)
        breakeven_reachable = True
        max_price_perpetual, growth_at_max_perpetual = target_price, breakeven
    except PriceUnreachableError as exc:
        breakeven = None
        breakeven_reachable = False
        max_price_perpetual = target_price + exc.best_price_gap
        growth_at_max_perpetual = exc.best_growth

    return ReverseDcfResult(
        ticker=ticker,
        target_price=target_price,
        implied_growth=g,
        ebit_margin=base.ebit_margin,
        median_roic=median_roic,
        terminal_roic=terminal_roic_value,
        implied_reinvestment_year1=implied_reinvestment_year1,
        implied_reinvestment_terminal=implied_reinvestment_terminal,
        wacc=base.wacc,
        terminal_growth=base.terminal_growth,
        breakeven_growth=breakeven,
        forecast_years=forecast_years,
        price_reachable=price_reachable,
        max_achievable_price_10y=max_price_10y,
        growth_at_max_achievable_price_10y=growth_at_max_10y,
        breakeven_reachable=breakeven_reachable,
        max_achievable_price_perpetual=max_price_perpetual,
        growth_at_max_achievable_price_perpetual=growth_at_max_perpetual,
        financials_source=financials_source,
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
    parser.add_argument(
        "--live-financials",
        action="store_true",
        help=(
            "C1 Day 23: fetch --ticker's 4-5 year financials from yfinance "
            "(reverse_dcf.live_financials) instead of reading --financials -- "
            "the 'reverse DCF lite' path for a ticker with no hand-entered CSV"
        ),
    )
    parser.add_argument(
        "--prices-csv",
        metavar="PATH",
        default=None,
        help=(
            "an OHLCV CSV (date,...,close,...) to read the latest close as the "
            "target price from, instead of --price or fixtures/market/<ticker>.csv "
            "-- e.g. STOCKSTALKER's own price fixture for a ticker with no "
            "reverse-dcf-engine market fixture"
        ),
    )
    args = parser.parse_args()

    financials_source = FINANCIALS_SOURCE_HAND
    if args.live_financials:
        live_path = ROOT / "outputs" / "live_financials" / f"{args.ticker.upper()}.csv"
        try:
            write_live_financials_csv(args.ticker, live_path)
        except (ValueError, OSError) as exc:
            print(f"! could not fetch live financials for {args.ticker}: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        args.financials = str(live_path)
        financials_source = FINANCIALS_SOURCE_LIVE

    market = None
    if args.prices_csv:
        prices_df = pd.read_csv(args.prices_csv)
        last_row = prices_df.iloc[-1]
        price = float(last_row["close"])
        price_source = f"{args.prices_csv} (last close, {last_row['date']})"
    elif args.price is None:
        market = load_market_price(args.ticker)
        price = market.price
        price_source = None
    else:
        price = args.price
        price_source = None

    result = solve(
        price,
        args.financials,
        ticker=args.ticker,
        forecast_years=args.years,
        terminal_growth=args.terminal_growth,
        financials_source=financials_source,
    )
    print(result.summary())
    if market is not None:
        print(f"(price Rs{market.price:,.2f} from {market.source_url}, as of {market.date})")
    elif price_source is not None:
        print(f"(price Rs{price:,.2f} from {price_source})")
    if args.live_financials:
        print(f"(financials: {financials_source})")

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
