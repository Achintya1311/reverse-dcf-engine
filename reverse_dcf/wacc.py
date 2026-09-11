"""Weighted average cost of capital module (Day 3).

Builds the WACC that Day 4's forward DCF and Day 5's reverse solver will
discount FCFF with. Every input is either:

- Damodaran's published India country equity risk premium and India
  industry-average beta (``fixtures/wacc/*.csv`` - fetched and cited in
  ``research/wacc_sources.md``), or
- derived straight from Gulf Oil Lubricants India's own financials
  (``data/GULFOILLUB/financials.csv``) - cost of debt, capital structure
  and the effective tax rate used to relever the industry beta.

Methodology, one line each:

- **Cost of equity** is CAPM: ``Re = Rf + beta_L * ERP_India``. ``beta_L``
  relevers the industry's *unlevered* beta to Gulf Oil's own D/E and tax
  rate (Hamada, zero-beta debt) rather than using the industry's average
  *levered* beta directly - the industry average bakes in whatever
  leverage the average Chemical (Basic) company in India happens to
  carry, which is not Gulf Oil's leverage.
- **Cost of debt** is ``interest_expense / average total_debt`` over the
  trailing two fiscal years (average, not year-end, to smooth a mid-year
  borrowing or repayment), after-tax at Gulf Oil's own effective tax rate
  for that year.
- **Capital structure** is book, not market: ``total_debt`` from the
  balance sheet against a book-equity proxy. See :func:`capital_structure`
  for exactly what that proxy assumes away.

Gulf Oil Lubricants India Limited (NSEI:GULFOILLUB) is classified
``Chemical (Basic)`` in Damodaran's own industry mapping
(``indname.xls``, "By company name" sheet) - see
``research/wacc_sources.md`` - not guessed from its lubricants business
description.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from reverse_dcf.financials import load_financials, to_numeric

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures" / "wacc"
DEFAULT_FINANCIALS = ROOT / "data" / "GULFOILLUB" / "financials.csv"


def load_india_erp(path: str | Path = FIXTURES / "india_country_risk_premium.csv") -> float:
    """India's total equity risk premium (mature-market ERP + country risk premium), as a decimal."""
    df = pd.read_csv(path)
    return float(df.loc[0, "equity_risk_premium_pct"]) / 100


def load_industry_beta(path: str | Path = FIXTURES / "india_industry_beta.csv") -> dict:
    """The Damodaran India industry-average beta row, as a dict (rates as decimals)."""
    df = pd.read_csv(path)
    row = df.iloc[0]
    return {
        "industry_name": row["industry_name"],
        "beta": float(row["beta"]),
        "de_ratio": float(row["de_ratio"]),
        "effective_tax_rate": float(row["effective_tax_rate_pct"]) / 100,
        "unlevered_beta": float(row["unlevered_beta"]),
    }


def load_risk_free_rate(path: str | Path = FIXTURES / "india_10y_gsec_yield.csv") -> float:
    """Most recent observation in the trailing risk-free-rate fixture, as a decimal."""
    df = pd.read_csv(path).sort_values("date")
    return float(df.iloc[-1]["yield_pct"]) / 100


def relever_beta(unlevered_beta: float, tax_rate: float, de_ratio: float) -> float:
    """Hamada: apply a target company's own leverage and tax rate to an industry unlevered beta."""
    return unlevered_beta * (1 + (1 - tax_rate) * de_ratio)


def cost_of_equity(risk_free_rate: float, beta: float, equity_risk_premium: float) -> float:
    """CAPM."""
    return risk_free_rate + beta * equity_risk_premium


def effective_tax_rate(ebit: float, interest_expense: float, tax_expense: float) -> float:
    """``tax_expense / pre-tax income``, where pre-tax income = ebit - interest_expense.

    Mirrors ``financials.py``'s derivation of ``ebit`` (profit before tax +
    finance costs), so pre-tax income falls out without a separate column.
    """
    pretax_income = ebit - interest_expense
    return tax_expense / pretax_income


@dataclass(frozen=True)
class CostOfDebt:
    interest_expense: float
    average_total_debt: float
    tax_rate: float

    @property
    def pretax(self) -> float:
        return self.interest_expense / self.average_total_debt

    @property
    def after_tax(self) -> float:
        return self.pretax * (1 - self.tax_rate)


def capital_structure(total_debt: float, total_assets: float) -> tuple[float, float]:
    """Return ``(weight_debt, weight_equity)`` from the balance sheet, as book values.

    Equity is a proxy: ``total_assets - total_debt``. The Day 2 schema
    carries no total-liabilities or book-equity column, so this folds every
    non-debt liability (trade payables, provisions, deferred tax) into the
    "equity" side - it overstates book equity and therefore understates the
    debt weight in WACC. See the README limitations section.
    """
    book_equity = total_assets - total_debt
    total_capital = total_debt + book_equity
    return total_debt / total_capital, book_equity / total_capital


@dataclass(frozen=True)
class WaccResult:
    fiscal_year: str
    risk_free_rate: float
    india_erp: float
    industry_name: str
    industry_unlevered_beta: float
    relevered_beta: float
    cost_of_equity: float
    cost_of_debt_pretax: float
    cost_of_debt_after_tax: float
    effective_tax_rate: float
    weight_debt: float
    weight_equity: float
    wacc: float

    def assumptions_block(self) -> str:
        lines = [
            f"WACC assumptions -- {self.fiscal_year} (Gulf Oil Lubricants India)",
            f"  Risk-free rate (India 10Y G-Sec, latest FRED obs.): {self.risk_free_rate:.2%}",
            f"  India equity risk premium (Damodaran):              {self.india_erp:.2%}",
            f"  Industry unlevered beta ({self.industry_name}, India): {self.industry_unlevered_beta:.4f}",
            f"  Relevered to Gulf Oil's own D/E and tax rate:       {self.relevered_beta:.4f}",
            f"  Cost of equity (CAPM):                              {self.cost_of_equity:.2%}",
            f"  Effective tax rate ({self.fiscal_year}):              {self.effective_tax_rate:.2%}",
            f"  Cost of debt, pre-tax:                               {self.cost_of_debt_pretax:.2%}",
            f"  Cost of debt, after-tax:                             {self.cost_of_debt_after_tax:.2%}",
            f"  Weight of debt / equity (book):                     {self.weight_debt:.2%} / {self.weight_equity:.2%}",
            f"  WACC:                                                {self.wacc:.2%}",
        ]
        return "\n".join(lines) + "\n"


def compute_wacc(financials_path: str | Path = DEFAULT_FINANCIALS, fiscal_year: str | None = None) -> WaccResult:
    """Compute Gulf Oil Lubricants India's WACC for one fiscal year.

    Defaults to the most recent fiscal year in ``financials_path`` - current
    capital structure and cost of debt are the standard WACC inputs, not a
    ten-year average. Needs the fiscal year immediately before the target
    one too, to average total debt for the cost-of-debt calculation.
    """
    df = to_numeric(load_financials(financials_path)).set_index("fiscal_year")
    years = list(df.index)
    if fiscal_year is None:
        fiscal_year = years[-1]
    if fiscal_year not in years:
        raise ValueError(f"fiscal year {fiscal_year!r} not in {financials_path}")
    idx = years.index(fiscal_year)
    if idx == 0:
        raise ValueError(f"no prior fiscal year before {fiscal_year} to average total_debt against")
    current = df.loc[fiscal_year]
    prior = df.loc[years[idx - 1]]

    tax_rate = effective_tax_rate(current["ebit"], current["interest_expense"], current["tax_expense"])
    debt = CostOfDebt(
        interest_expense=current["interest_expense"],
        average_total_debt=(current["total_debt"] + prior["total_debt"]) / 2,
        tax_rate=tax_rate,
    )

    industry = load_industry_beta()
    de_ratio = current["total_debt"] / (current["total_assets"] - current["total_debt"])
    beta_l = relever_beta(industry["unlevered_beta"], tax_rate, de_ratio)

    rf = load_risk_free_rate()
    erp = load_india_erp()
    re = cost_of_equity(rf, beta_l, erp)

    weight_debt, weight_equity = capital_structure(current["total_debt"], current["total_assets"])
    wacc = weight_equity * re + weight_debt * debt.after_tax

    return WaccResult(
        fiscal_year=fiscal_year,
        risk_free_rate=rf,
        india_erp=erp,
        industry_name=industry["industry_name"],
        industry_unlevered_beta=industry["unlevered_beta"],
        relevered_beta=beta_l,
        cost_of_equity=re,
        cost_of_debt_pretax=debt.pretax,
        cost_of_debt_after_tax=debt.after_tax,
        effective_tax_rate=tax_rate,
        weight_debt=weight_debt,
        weight_equity=weight_equity,
        wacc=wacc,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--financials", default=str(DEFAULT_FINANCIALS))
    parser.add_argument("--fiscal-year", default=None, help="defaults to the most recent year in the CSV")
    args = parser.parse_args()
    result = compute_wacc(args.financials, args.fiscal_year)
    print(result.assumptions_block())


if __name__ == "__main__":
    main()
