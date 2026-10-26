"""Attack the conclusion, mechanically (Day 9).

``NEXT_STEPS.md``'s Day 9 row has no artifact of its own - the output is
"hardened thesis", not a file - but a claim that survived being attacked is
only worth something if the attack actually ran against the same committed
fixtures everything else in this project uses, rather than living as prose
in a limitations section nobody re-executes. This module is that: two
checks against the two modeling choices most likely to be doing invisible
work in Day 8's headline finding, neither previously varied anywhere in
Days 1-8.

1. **Base-year robustness** (:func:`base_year_robustness_check`). The
   README's own limitations section already flags FY2014-15 as "not a
   normal first year" - Gulf Oil was a shell company until a Scheme of
   Arrangement transferred the lubricants business in that fiscal year.
   If that year understates Gulf Oil's true run-rate, Day 6's realized
   10-year CAGR (14.54%, used as the "history" side of the whole
   comparison) could be inflated by an unrepresentative base year -
   narrowing, not widening, the gap the headline finding rests on. This
   recomputes that CAGR with FY2014-15 dropped, using
   :func:`reverse_dcf.compare.historical_revenue_cagr`'s new
   ``skip_years`` argument.

2. **Forecast-horizon robustness** (:func:`horizon_sensitivity`). Every
   number in ``REPORT.md`` uses ``forecast_years=10`` by convention - never
   varied against anything else in Days 1-8. This reruns Day 5's solver at
   a spread of horizons to check whether the negative-implied-growth
   finding is an artifact of that specific choice rather than a robust
   read of the price.

3. **ROIC-anchor-window robustness** (:func:`roic_anchor_robustness_check`,
   V14 in CRITIQUES.md). ``historical_median_roic`` anchors the whole
   fade schedule on the full fiscal-year history - a third modeling
   choice this module never varied, despite its own stated mandate to
   test exactly this class of thing. GULFOILLUB's own realized ROIC has a
   visible declining trend, so a recent trailing window could anchor the
   schedule materially lower than the full history does. This reruns the
   headline 10-year solve with the anchor built from only the most recent
   fiscal years, and reports whether that changes the reachability
   conclusion.

All three are read, not asserted: if any attack had actually broken the
headline finding, the fix belongs in ``REPORT.md``, not in this module
weakening the check until it passes.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from reverse_dcf.compare import historical_revenue_cagr
from reverse_dcf.forward import DEFAULT_FINANCIALS
from reverse_dcf.financials import load_financials, to_numeric
from reverse_dcf.solve import PriceUnreachableError, implied_growth, load_market_price, perpetual_breakeven_growth, solve
from reverse_dcf.wacc import compute_wacc


def base_year_robustness_check(financials_path=DEFAULT_FINANCIALS) -> dict:
    """Realized revenue CAGR with vs. without the flagged FY2014-15 restructuring year as base.

    Returns both figures plus whether dropping the flagged year *weakens*
    the base-case realized CAGR (the failure mode this check exists to
    catch) or not.
    """
    with_restructuring_year = historical_revenue_cagr(financials_path)
    without_restructuring_year = historical_revenue_cagr(financials_path, skip_years=1)
    return {
        "with_fy2014_15": with_restructuring_year,
        "without_fy2014_15": without_restructuring_year,
        "weakens_finding": bool(without_restructuring_year < with_restructuring_year),
    }


DEFAULT_HORIZONS = (5, 7, 10, 12, 15)


@dataclass(frozen=True)
class HorizonResult:
    """One forecast horizon's implied growth, or how close it got.

    ``growth`` is ``None`` exactly when ``reachable`` is ``False``. V9
    (CRITIQUES.md, Day 30): rather than discarding
    :class:`reverse_dcf.solve.PriceUnreachableError`'s own ``best_growth``/
    ``best_price_gap`` down to a bare ``None``, an unreachable horizon keeps
    its ceiling -- the closest price this horizon's bracket can reach
    (``ceiling_price``) and the growth rate that gets there
    (``ceiling_growth``) -- so a caller can report *how* unreachable that
    horizon is, not just that it is, the same information :func:`reverse_dcf.solve.solve`
    already surfaces for the base-case 10-year horizon via
    ``max_achievable_price_10y``/``growth_at_max_achievable_price_10y``.
    """

    growth: float | None
    reachable: bool
    ceiling_price: float | None
    ceiling_growth: float | None


def horizon_sensitivity(
    target_price: float,
    financials_path=DEFAULT_FINANCIALS,
    *,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> dict[int, HorizonResult]:
    """10-year-equivalent implied growth at each forecast horizon in ``horizons``.

    Every other assumption stays at :func:`reverse_dcf.forward.base_case_from_financials`'s
    defaults (Day 5's base case), same as the headline ``forecast_years=10`` run - only
    the horizon changes.

    V2 (CRITIQUES.md V1): a horizon's result is unreachable when
    :func:`reverse_dcf.solve.implied_growth` raises
    :class:`reverse_dcf.solve.PriceUnreachableError` at that horizon -- no
    longer a hypothetical, since V2 fixing the growth/reinvestment identity
    means longer horizons (more years paying V2's reinvestment cost for the
    same growth) can themselves push the target price out of reach even
    when a shorter horizon still reaches it. That horizon-dependence is
    itself part of what this check exists to surface, not a reason to hide
    the horizon behind a crash.
    """
    result = {}
    for years in horizons:
        try:
            g = implied_growth(target_price, financials_path, forecast_years=years)
            result[years] = HorizonResult(growth=g, reachable=True, ceiling_price=None, ceiling_growth=None)
        except PriceUnreachableError as exc:
            result[years] = HorizonResult(
                growth=None,
                reachable=False,
                ceiling_price=target_price + exc.best_price_gap,
                ceiling_growth=exc.best_growth,
            )
    return result


DEFAULT_ROIC_ANCHOR_WINDOWS = (3, 4, 5)


def _implied_growth_or_ceiling(
    target_price: float,
    financials_path,
    forecast_years: int,
    *,
    roic_anchor_years: int | None,
) -> HorizonResult:
    try:
        g = implied_growth(
            target_price, financials_path, forecast_years=forecast_years, roic_anchor_years=roic_anchor_years
        )
        return HorizonResult(growth=g, reachable=True, ceiling_price=None, ceiling_growth=None)
    except PriceUnreachableError as exc:
        return HorizonResult(
            growth=None,
            reachable=False,
            ceiling_price=target_price + exc.best_price_gap,
            ceiling_growth=exc.best_growth,
        )


def roic_anchor_robustness_check(
    target_price: float,
    financials_path=DEFAULT_FINANCIALS,
    *,
    forecast_years: int = 10,
    windows: tuple[int, ...] = DEFAULT_ROIC_ANCHOR_WINDOWS,
) -> dict:
    """The headline ``forecast_years``-horizon reachability, full-history ROIC anchor vs. a recent trailing window.

    V14 (CRITIQUES.md): no check existed for which fiscal years anchor
    :func:`reverse_dcf.forward.historical_median_roic`, the third modeling
    choice this module's own mandate names alongside base year
    (:func:`base_year_robustness_check`) and forecast horizon
    (:func:`horizon_sensitivity`). Mirrors ``base_year_robustness_check``'s
    "recompute the headline figure under a different slice of history"
    shape: a ``full_history`` baseline, one result per trailing window in
    ``windows`` (via :func:`reverse_dcf.solve.implied_growth`'s
    ``roic_anchor_years``), and whether any window flips the baseline's
    reachability conclusion -- read, not assumed, the same restraint this
    module's docstring states for the other two checks.
    """
    full_history = _implied_growth_or_ceiling(
        target_price, financials_path, forecast_years, roic_anchor_years=None
    )
    by_window = {
        years: _implied_growth_or_ceiling(target_price, financials_path, forecast_years, roic_anchor_years=years)
        for years in windows
    }
    return {
        "full_history": full_history,
        "by_window": by_window,
        "changes_reachability": any(r.reachable != full_history.reachable for r in by_window.values()),
    }


@dataclass(frozen=True)
class CapitalStructureResult:
    """V22: one WACC basis and what the 10-year and perpetual solves give at it."""

    wacc: float
    weight_debt: float
    reachable_10y: bool
    ceiling_10y: float | None
    reachable_perpetual: bool
    ceiling_perpetual: float | None


def _at_wacc(target_price: float, financials_path, wacc_result) -> CapitalStructureResult:
    try:
        implied_growth(target_price, financials_path, wacc=wacc_result.wacc)
        reachable_10y, ceiling_10y = True, None
    except PriceUnreachableError as exc:
        reachable_10y, ceiling_10y = False, target_price + exc.best_price_gap
    try:
        perpetual_breakeven_growth(target_price, financials_path, wacc=wacc_result.wacc)
        reachable_perpetual, ceiling_perpetual = True, None
    except PriceUnreachableError as exc:
        reachable_perpetual, ceiling_perpetual = False, target_price + exc.best_price_gap
    return CapitalStructureResult(
        wacc=wacc_result.wacc,
        weight_debt=wacc_result.weight_debt,
        reachable_10y=reachable_10y,
        ceiling_10y=ceiling_10y,
        reachable_perpetual=reachable_perpetual,
        ceiling_perpetual=ceiling_perpetual,
    )


def market_weights_check(target_price: float, financials_path=DEFAULT_FINANCIALS) -> dict:
    """V22 (CRITIQUES.md): rerun the undated solves with WACC at market rather than book weights.

    The README's Limitations name book weights as a known bias (equity
    proxied by total assets less debt). Market capitalisation is
    ``target_price`` times the latest fiscal year's share count, in the
    financials' lakh units. The base case stays at book weights.
    """
    shares = to_numeric(load_financials(financials_path))["shares_outstanding"].iloc[-1]
    market_cap = target_price * shares / 100_000
    return {
        "book": _at_wacc(target_price, financials_path, compute_wacc(financials_path)),
        "market": _at_wacc(target_price, financials_path, compute_wacc(financials_path, market_cap=market_cap)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="GULFOILLUB")
    parser.add_argument("--financials", default=str(DEFAULT_FINANCIALS))
    parser.add_argument("--price", type=float, default=None, help="current market price; defaults to fixtures/market/<ticker>.csv")
    args = parser.parse_args()

    market = load_market_price(args.ticker) if args.price is None else None
    price = args.price if args.price is not None else market.price

    print(f"Day 9 -- attacking the conclusion, {args.ticker} at Rs{price:,.2f}/share\n")

    base_year = base_year_robustness_check(args.financials)
    print("1. Base-year robustness (drop FY2014-15, the flagged restructuring year):")
    print(f"   realized CAGR with FY2014-15 as base:    {base_year['with_fy2014_15']:.2%}")
    print(f"   realized CAGR with FY2015-16 as base:    {base_year['without_fy2014_15']:.2%}")
    verdict = "WEAKENS the finding" if base_year["weakens_finding"] else "does not weaken the finding"
    print(f"   -> dropping the flagged year {verdict}\n")

    print("2. Forecast-horizon robustness (Day 5's solver at horizons other than the default 10y):")
    for years, r in horizon_sensitivity(price, args.financials).items():
        marker = " <- base case" if years == 10 else ""
        if r.reachable:
            value = f"{r.growth:+.2%}"
        else:
            value = (
                "unreachable (V2: no growth rate reproduces this price at this horizon -- "
                f"ceiling Rs{r.ceiling_price:,.2f}/share at {r.ceiling_growth:+.2%} growth)"
            )
        print(f"   {years:>2}y horizon: implied growth {value}{marker}")

    print("\n3. ROIC-anchor-window robustness (median ROIC from the full history vs. a recent trailing window):")
    roic_anchor = roic_anchor_robustness_check(price, args.financials)

    def _fmt(r: HorizonResult) -> str:
        if r.reachable:
            return f"{r.growth:+.2%}"
        return (
            "unreachable (no growth rate reproduces this price under this anchor -- "
            f"ceiling Rs{r.ceiling_price:,.2f}/share at {r.ceiling_growth:+.2%} growth)"
        )

    print(f"   full history:        implied growth {_fmt(roic_anchor['full_history'])} <- base case")
    for years, r in roic_anchor["by_window"].items():
        print(f"   trailing {years}y anchor: implied growth {_fmt(r)}")
    verdict = (
        "CHANGES the reachability conclusion" if roic_anchor["changes_reachability"] else "does not change the reachability conclusion"
    )
    print(f"   -> anchoring on a recent window {verdict}")

    print("\n4. Valuation-date check (V18: the base-year value carried to the price date):")
    if market is None:
        print("   skipped: --price has no date to carry the value to")
    else:
        _print_dated_check(price, args.financials, args.ticker, market.date)

    print("\n5. Capital-structure check (V22: WACC at market rather than book weights, undated solves):")
    weights = market_weights_check(price, args.financials)

    def _ceiling(reachable: bool, ceiling: float | None) -> str:
        return "reachable" if reachable else f"unreachable, ceiling Rs{ceiling:,.2f}"

    for basis in ("book", "market"):
        r = weights[basis]
        marker = " <- base case" if basis == "book" else ""
        print(
            f"   {basis + ' weights:':<15} WACC {r.wacc:.2%} (debt {r.weight_debt:.2%}); "
            f"10y {_ceiling(r.reachable_10y, r.ceiling_10y)}; "
            f"perpetual {_ceiling(r.reachable_perpetual, r.ceiling_perpetual)}{marker}"
        )
    changes = (weights["book"].reachable_10y, weights["book"].reachable_perpetual) != (
        weights["market"].reachable_10y,
        weights["market"].reachable_perpetual,
    )
    verdict = "CHANGES the reachability conclusion" if changes else "does not change the reachability conclusion"
    print(f"   -> using market weights {verdict}")


def _print_dated_check(price, financials, ticker, price_date) -> None:
    dated = solve(price, financials, ticker=ticker, price_date=price_date)
    undated = "reachable" if dated.price_reachable else f"unreachable (ceiling Rs{dated.max_achievable_price_10y:,.2f})"
    print(f"   as of {dated.base_fiscal_year} year end:  {undated} <- base case")
    if dated.price_reachable_dated:
        value = f"implied growth {dated.implied_growth_dated:+.2%}"
    else:
        value = "unreachable"
    print(
        f"   dated to {dated.price_date} ({dated.years_to_price_date:.2f} years later): {value} "
        f"(ceiling Rs{dated.max_achievable_price_10y_dated:,.2f}/share)"
    )
    verdict = (
        "CHANGES the reachability conclusion"
        if dated.price_reachable_dated != dated.price_reachable
        else "does not change the reachability conclusion"
    )
    print(f"   -> dating the value to the price {verdict} (elapsed years are modelled, not reported: S25)")


if __name__ == "__main__":
    main()
