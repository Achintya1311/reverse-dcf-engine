"""Forward FCFF DCF engine (Day 4).

Prices a company from an explicit set of assumptions, exactly the ordinary
direction: growth, margin and reinvestment go in, an implied share price
comes out. Day 5's reverse solver runs this engine inside a root-finder,
searching for the growth rate that makes the implied price equal today's
market price -- so every number this module needs must arrive as an
argument. There is nothing in here that hardcodes Gulf Oil, a fiscal year,
or a rate; :func:`base_case_from_financials` is the only place that reads
the committed data, and it does so by loading the latest fiscal year and
Day 3's WACC module, not by pasting numbers into the formulas.

Method, one line each:

- **Revenue** grows at a single constant rate for ``forecast_years``, then
  the terminal-value formula assumes the same constant-growth structure
  forever at (usually a slower) ``terminal_growth``. This is the
  single-stage-plus-terminal shape the README's limitations section already
  names -- a business mid-transition (a margin ramp, a reinvestment step
  change) is not well described by one constant growth rate.
- **FCFF** = EBIT x (1 - tax_rate) x (1 - reinvestment_rate). This is the
  standard reinvestment-rate formulation (Damodaran): reinvestment_rate is
  ``(capex - D&A + change in NWC) / NOPAT``, so the one rate absorbs capex,
  depreciation and working-capital movement instead of forecasting each
  separately -- see :func:`historical_reinvestment_rate`.
- **Terminal value** is the Gordon growth formula on the first
  post-forecast FCFF, discounted back at the same WACC used for the
  explicit period. Requires ``wacc > terminal_growth``; that is not a
  numerical nicety, a perpetuity growing faster than its discount rate has
  no finite present value.
- **Equity value** = enterprise value - net debt (total debt - cash), at
  the same balance-sheet snapshot the WACC module used.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from reverse_dcf.financials import load_financials, to_numeric
from reverse_dcf.wacc import DEFAULT_FINANCIALS, compute_wacc, effective_tax_rate, load_risk_free_rate

LAKH_TO_RUPEES = 100_000
"""``data/GULFOILLUB/financials.csv`` reports every rupee figure in lakh (confirmed
against the README's ``96748.17`` FY2014-15 revenue = "₹967.5 cr"). ``shares_outstanding``
is a raw share count, not in lakh, so :func:`base_case_from_financials` converts every
rupee-denominated column to actual rupees before building :class:`DcfAssumptions` -
otherwise ``implied_share_price`` comes out in lakh-per-share, three orders of
magnitude too small."""


def project_revenue(revenue_base: float, growth_rate: float, years: int) -> list[float]:
    """Revenue for each of the next ``years`` years at a constant growth rate.

    Index 0 of the result is year 1 (``revenue_base`` grown once), not year 0.
    """
    if years < 1:
        raise ValueError("years must be at least 1")
    return [revenue_base * (1 + growth_rate) ** t for t in range(1, years + 1)]


def fcff_from_revenue(revenue: float, ebit_margin: float, tax_rate: float, reinvestment_rate: float) -> float:
    """FCFF = EBIT x (1 - tax) x (1 - reinvestment_rate) for one year's revenue."""
    ebit = revenue * ebit_margin
    nopat = ebit * (1 - tax_rate)
    return nopat * (1 - reinvestment_rate)


def project_fcff(revenues: list[float], ebit_margin: float, tax_rate: float, reinvestment_rate: float) -> list[float]:
    """FCFF for each year in ``revenues``, same margin/tax/reinvestment assumptions throughout."""
    return [fcff_from_revenue(r, ebit_margin, tax_rate, reinvestment_rate) for r in revenues]


def present_value(cashflows: list[float], wacc: float) -> float:
    """Sum of ``cashflows`` discounted at ``wacc``, cashflows[0] received at t=1."""
    return sum(cf / (1 + wacc) ** t for t, cf in enumerate(cashflows, start=1))


def terminal_value(final_year_fcff: float, wacc: float, terminal_growth: float) -> float:
    """Gordon growth terminal value, as of the end of the explicit forecast (not discounted to today)."""
    if wacc <= terminal_growth:
        raise ValueError(
            f"wacc ({wacc:.4f}) must exceed terminal_growth ({terminal_growth:.4f}) "
            "for the terminal perpetuity to have a finite value"
        )
    next_year_fcff = final_year_fcff * (1 + terminal_growth)
    return next_year_fcff / (wacc - terminal_growth)


def historical_reinvestment_rate(df_row: "pd.Series", prior_row: "pd.Series", tax_rate: float) -> float:
    """Reinvestment rate implied by one fiscal year's reported figures.

    ``(capex - D&A + change in net working capital) / NOPAT``. NOPAT is
    recomputed from ``ebit`` and ``tax_rate`` rather than taken from
    ``net_profit``, since NOPAT is unlevered (pre-interest) and net_profit
    is not.
    """
    nopat = df_row["ebit"] * (1 - tax_rate)
    change_in_nwc = df_row["net_working_capital"] - prior_row["net_working_capital"]
    reinvestment = df_row["capex"] - df_row["depreciation_amortization"] + change_in_nwc
    return reinvestment / nopat


@dataclass(frozen=True)
class DcfAssumptions:
    revenue_base: float
    revenue_growth: float
    ebit_margin: float
    tax_rate: float
    reinvestment_rate: float
    wacc: float
    terminal_growth: float
    forecast_years: int
    net_debt: float
    shares_outstanding: float


@dataclass(frozen=True)
class DcfResult:
    assumptions: DcfAssumptions
    revenues: list[float]
    fcffs: list[float]
    pv_explicit_fcff: float
    pv_terminal_value: float
    enterprise_value: float
    equity_value: float
    implied_share_price: float

    def summary(self) -> str:
        a = self.assumptions
        lines = [
            f"Forward FCFF DCF -- {a.forecast_years}-year forecast",
            f"  Revenue growth (explicit period):   {a.revenue_growth:.2%}",
            f"  EBIT margin:                        {a.ebit_margin:.2%}",
            f"  Tax rate:                           {a.tax_rate:.2%}",
            f"  Reinvestment rate:                  {a.reinvestment_rate:.2%}",
            f"  WACC:                               {a.wacc:.2%}",
            f"  Terminal growth:                    {a.terminal_growth:.2%}",
            f"  PV of explicit-period FCFF:          {self.pv_explicit_fcff:,.2f}",
            f"  PV of terminal value:                {self.pv_terminal_value:,.2f}",
            f"  Enterprise value:                    {self.enterprise_value:,.2f}",
            f"  Net debt:                            {a.net_debt:,.2f}",
            f"  Equity value:                        {self.equity_value:,.2f}",
            f"  Shares outstanding:                  {a.shares_outstanding:,.0f}",
            f"  Implied share price:                 {self.implied_share_price:,.2f}",
        ]
        return "\n".join(lines) + "\n"


def run_dcf(assumptions: DcfAssumptions) -> DcfResult:
    """Run the forward DCF end to end: assumptions in, an implied share price out."""
    revenues = project_revenue(assumptions.revenue_base, assumptions.revenue_growth, assumptions.forecast_years)
    fcffs = project_fcff(revenues, assumptions.ebit_margin, assumptions.tax_rate, assumptions.reinvestment_rate)

    pv_explicit = present_value(fcffs, assumptions.wacc)
    tv = terminal_value(fcffs[-1], assumptions.wacc, assumptions.terminal_growth)
    pv_terminal = tv / (1 + assumptions.wacc) ** assumptions.forecast_years

    enterprise_value = pv_explicit + pv_terminal
    equity_value = enterprise_value - assumptions.net_debt
    implied_share_price = equity_value / assumptions.shares_outstanding

    return DcfResult(
        assumptions=assumptions,
        revenues=revenues,
        fcffs=fcffs,
        pv_explicit_fcff=pv_explicit,
        pv_terminal_value=pv_terminal,
        enterprise_value=enterprise_value,
        equity_value=equity_value,
        implied_share_price=implied_share_price,
    )


def base_case_from_financials(
    financials_path: str | Path = DEFAULT_FINANCIALS,
    *,
    revenue_growth: float,
    forecast_years: int = 10,
    terminal_growth: float | None = None,
) -> DcfAssumptions:
    """Build a :class:`DcfAssumptions` off the latest fiscal year's actuals and Day 3's WACC.

    Only ``revenue_growth`` has no sensible default -- it is the number
    Day 5's solver exists to find, so this function refuses to guess one.
    Every other assumption is read from data: EBIT margin, tax rate and
    reinvestment rate from the latest fiscal year in ``financials_path``,
    WACC from :func:`reverse_dcf.wacc.compute_wacc`, and terminal growth
    defaults to the same risk-free rate WACC uses, on Damodaran's own
    convention that a perpetual growth rate should not exceed the economy's
    long-run (proxied by the risk-free) growth rate.
    """
    df = to_numeric(load_financials(financials_path)).set_index("fiscal_year")
    years = list(df.index)
    if len(years) < 2:
        raise ValueError("need at least two fiscal years to derive a reinvestment rate")
    current = df.loc[years[-1]]
    prior = df.loc[years[-2]]

    tax_rate = effective_tax_rate(current["ebit"], current["interest_expense"], current["tax_expense"])
    ebit_margin = current["ebit"] / current["revenue"]
    reinvestment_rate = historical_reinvestment_rate(current, prior, tax_rate)

    wacc_result = compute_wacc(financials_path, fiscal_year=years[-1])
    if terminal_growth is None:
        terminal_growth = load_risk_free_rate()

    net_debt_lakh = current["total_debt"] - current["cash_and_equivalents"]
    return DcfAssumptions(
        revenue_base=current["revenue"] * LAKH_TO_RUPEES,
        revenue_growth=revenue_growth,
        ebit_margin=ebit_margin,
        tax_rate=tax_rate,
        reinvestment_rate=reinvestment_rate,
        wacc=wacc_result.wacc,
        terminal_growth=terminal_growth,
        forecast_years=forecast_years,
        net_debt=net_debt_lakh * LAKH_TO_RUPEES,
        shares_outstanding=current["shares_outstanding"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--financials", default=str(DEFAULT_FINANCIALS))
    parser.add_argument("--growth", type=float, required=True, help="explicit-period revenue growth, e.g. 0.10")
    parser.add_argument("--years", type=int, default=10, help="explicit forecast horizon in years")
    parser.add_argument(
        "--terminal-growth",
        type=float,
        default=None,
        help="defaults to the current India risk-free rate (fixtures/wacc/india_10y_gsec_yield.csv)",
    )
    parser.add_argument(
        "--margin",
        type=float,
        default=None,
        help="EBIT margin override; defaults to the latest fiscal year's actual margin",
    )
    parser.add_argument(
        "--reinvestment-rate",
        type=float,
        default=None,
        help="reinvestment rate override; defaults to the latest fiscal year's implied rate",
    )
    args = parser.parse_args()

    assumptions = base_case_from_financials(
        args.financials,
        revenue_growth=args.growth,
        forecast_years=args.years,
        terminal_growth=args.terminal_growth,
    )
    if args.margin is not None:
        assumptions = DcfAssumptions(**{**assumptions.__dict__, "ebit_margin": args.margin})
    if args.reinvestment_rate is not None:
        assumptions = DcfAssumptions(**{**assumptions.__dict__, "reinvestment_rate": args.reinvestment_rate})

    result = run_dcf(assumptions)
    print(result.summary())
    print(f"(Enterprise/equity value in rupees; ₹{result.enterprise_value / 1e7:,.1f} cr enterprise value)")


if __name__ == "__main__":
    main()
