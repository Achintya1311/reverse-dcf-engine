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

Both are read, not asserted: if either attack had actually broken the
headline finding, the fix belongs in ``REPORT.md``, not in this module
weakening the check until it passes.
"""

from __future__ import annotations

import argparse

from reverse_dcf.compare import historical_revenue_cagr
from reverse_dcf.forward import DEFAULT_FINANCIALS
from reverse_dcf.solve import implied_growth, load_market_price


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


def horizon_sensitivity(
    target_price: float,
    financials_path=DEFAULT_FINANCIALS,
    *,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> dict[int, float]:
    """10-year-equivalent implied growth at each forecast horizon in ``horizons``.

    Every other assumption stays at :func:`reverse_dcf.forward.base_case_from_financials`'s
    defaults (Day 5's base case), same as the headline ``forecast_years=10`` run - only
    the horizon changes.
    """
    return {years: implied_growth(target_price, financials_path, forecast_years=years) for years in horizons}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="GULFOILLUB")
    parser.add_argument("--financials", default=str(DEFAULT_FINANCIALS))
    parser.add_argument("--price", type=float, default=None, help="current market price; defaults to fixtures/market/<ticker>.csv")
    args = parser.parse_args()

    price = args.price if args.price is not None else load_market_price(args.ticker).price

    print(f"Day 9 -- attacking the conclusion, {args.ticker} at Rs{price:,.2f}/share\n")

    base_year = base_year_robustness_check(args.financials)
    print("1. Base-year robustness (drop FY2014-15, the flagged restructuring year):")
    print(f"   realized CAGR with FY2014-15 as base:    {base_year['with_fy2014_15']:.2%}")
    print(f"   realized CAGR with FY2015-16 as base:    {base_year['without_fy2014_15']:.2%}")
    verdict = "WEAKENS the finding" if base_year["weakens_finding"] else "does not weaken the finding"
    print(f"   -> dropping the flagged year {verdict}\n")

    print("2. Forecast-horizon robustness (Day 5's solver at horizons other than the default 10y):")
    for years, g in horizon_sensitivity(price, args.financials).items():
        marker = " <- base case" if years == 10 else ""
        print(f"   {years:>2}y horizon: implied growth {g:+.2%}{marker}")


if __name__ == "__main__":
    main()
