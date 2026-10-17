"""C1 Day 23: a yfinance-based financials adapter, so the reverse DCF can run
a simplified ("lite") version against any NSE ticker with public financial
statements, not just GULFOILLUB's hand-transcribed ten-year history.

Builds a :data:`reverse_dcf.financials.REQUIRED_COLUMNS`-shaped table from
yfinance's own annual income statement, balance sheet and cash flow
statement -- 4-5 fiscal years, consolidated, not GULFOILLUB's ten
hand-transcribed years cited year by year in ``research/sources.md``.
:data:`FINANCIALS_SOURCE_LIVE` labels every contract built this way, so
nothing downstream (STOCKSTALKER's front door, the README, the site) reads
it as the same depth or definitions as the hand-entered data.

Known, deliberate simplifications of this "lite" path, not bugs:

- ``net_working_capital`` is yfinance's plain
  ``WorkingCapital = current assets - current liabilities``, not
  GULFOILLUB's own cash/debt-adjusted definition (see ``financials.py``'s
  module docstring) -- the two are not directly comparable.
- ``depreciation_amortization``, ``interest_expense`` and ``cash_and_equivalents``
  come from whichever of yfinance's own line items is actually populated for
  a given issuer (a fallback chain, see ``_INCOME_DA_FIELDS`` etc.), not a
  single fixed definition checked against a source PDF.
- :func:`reverse_dcf.wacc.compute_wacc` still prices every ticker against
  Gulf Oil's own India "Chemical (Basic)" industry beta fixture -- there is
  no free per-sector beta source wired up yet, so this is a known,
  documented approximation for any ticker outside that industry, not a
  silent one.

Communication with the rest of the pipeline stays by file, the same
convention every other satellite contract uses: this module writes a CSV in
exactly the shape ``reverse_dcf.financials.load_financials`` reads, so
``base_case_from_financials``/``compute_wacc``/``solve`` never need to know
whether their input came from a hand-entered file or a live fetch.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from reverse_dcf.financials import REQUIRED_COLUMNS

FINANCIALS_SOURCE_LIVE = "yfinance, consolidated, 4-5 years"
FINANCIALS_SOURCE_HAND = "hand-entered, 10-year (GULFOILLUB base case)"

LAKH = 100_000
MIN_FISCAL_YEARS = 2
MAX_FISCAL_YEARS = 5

# yfinance's own row label for each line item, tried in order -- different
# issuers omit different rows (e.g. an issuer with no reported D&A line in
# the income statement carries it only in the cash flow statement instead),
# so each of these is a fallback chain, not a single fixed key.
_INCOME_FIELDS: dict[str, list[str]] = {
    "revenue": ["TotalRevenue"],
    "ebitda": ["EBITDA"],
    "ebit": ["EBIT", "OperatingIncome"],
    "interest_expense": ["InterestExpense", "InterestExpenseNonOperating"],
    "tax_expense": ["TaxProvision"],
    "net_profit": ["NetIncome", "NetIncomeCommonStockholders"],
}
_INCOME_DA_FIELDS = ["DepreciationAndAmortizationInIncomeStatement", "DepreciationIncomeStatement"]
_CASHFLOW_DA_FIELDS = ["DepreciationAndAmortization", "Depreciation"]

_BALANCE_FIELDS: dict[str, list[str]] = {
    "total_assets": ["TotalAssets"],
    "total_debt": ["TotalDebt"],
    "net_working_capital": ["WorkingCapital"],
    "shares_outstanding": ["OrdinarySharesNumber", "ShareIssued"],
}
_CASHFLOW_FIELDS: dict[str, list[str]] = {
    "cash_and_equivalents": ["EndCashPosition"],
    "capex": ["CapitalExpenditure"],
}


def _first_available(statement: pd.DataFrame, keys: list[str], column: Any) -> float | None:
    """The first of ``keys`` present as a row label in ``statement`` with a non-null value at ``column``."""
    for key in keys:
        if key in statement.index:
            value = statement.loc[key, column]
            if pd.notna(value):
                return float(value)
    return None


def _fiscal_year_label(period_end: pd.Timestamp) -> str:
    """"FY{start}-{end}" from a statement column's period-end timestamp.

    Indian fiscal years run April to March, so a statement ending in
    calendar year Y covers fiscal "FY{Y-1}-{Y's last two digits}" -- the
    same convention ``tests/test_financials_schema.py`` already checks
    GULFOILLUB's hand-entered labels against.
    """
    end_year = period_end.year
    return f"FY{end_year - 1}-{str(end_year)[2:]}"


def _to_yf_symbol(ticker: str) -> str:
    """Bare NSE symbol to the yfinance-suffixed form, idempotently.

    Callers (this repo's own CLI, and STOCKSTALKER's subprocess wiring,
    which passes the same bare symbol it uses everywhere else -- see
    ``stockstalker.run.to_yf_ticker``) may hand either form.
    """
    ticker = ticker.upper().strip()
    return ticker if ticker.endswith(".NS") else f"{ticker}.NS"


def fetch_yfinance_financials(ticker: str, max_years: int = MAX_FISCAL_YEARS) -> pd.DataFrame:
    """Build a :data:`reverse_dcf.financials.REQUIRED_COLUMNS`-shaped table for ``ticker``
    from yfinance's annual statements, oldest fiscal year first.

    Raises ``ValueError`` if yfinance has no statements for ``ticker``, or
    fewer than :data:`MIN_FISCAL_YEARS` fiscal years with every required
    field present (too thin a history to derive even one year-over-year
    reinvestment rate). The caller's job is to report that as "no live
    data for this ticker" -- never to crash on it.
    """
    import yfinance as yf  # imported lazily: only this live path needs it,
    # not every other reverse_dcf module (same reasoning STOCKSTALKER's
    # live_contracts.py gives for shelling out to mcsim/factors rather
    # than importing them unconditionally).

    yf_ticker = yf.Ticker(_to_yf_symbol(ticker))
    income = yf_ticker.get_income_stmt(freq="yearly")
    balance = yf_ticker.get_balance_sheet(freq="yearly")
    cashflow = yf_ticker.get_cashflow(freq="yearly")
    if income is None or income.empty or balance is None or balance.empty or cashflow is None or cashflow.empty:
        raise ValueError(f"yfinance returned no annual financial statements for {ticker!r}")

    # Match columns across the three statements by fiscal year-end, not by
    # position -- yfinance has been seen to carry a different column count
    # per statement for the same issuer.
    income_years = {c.year: c for c in income.columns}
    balance_years = {c.year: c for c in balance.columns}
    cashflow_years = {c.year: c for c in cashflow.columns}
    common_years = sorted(set(income_years) & set(balance_years) & set(cashflow_years))[-max_years:]

    rows = []
    for year in common_years:
        ic, bc, cc = income_years[year], balance_years[year], cashflow_years[year]

        da = _first_available(income, _INCOME_DA_FIELDS, ic)
        if da is None:
            da = _first_available(cashflow, _CASHFLOW_DA_FIELDS, cc)
        ebitda = _first_available(income, _INCOME_FIELDS["ebitda"], ic)
        ebit = _first_available(income, _INCOME_FIELDS["ebit"], ic)
        if da is None and ebitda is not None and ebit is not None:
            da = ebitda - ebit

        capex_raw = _first_available(cashflow, _CASHFLOW_FIELDS["capex"], cc)
        interest_expense_raw = _first_available(income, _INCOME_FIELDS["interest_expense"], ic)
        tax_expense_raw = _first_available(income, _INCOME_FIELDS["tax_expense"], ic)

        values: dict[str, float | None] = {
            "revenue": _first_available(income, _INCOME_FIELDS["revenue"], ic),
            "ebitda": ebitda,
            "depreciation_amortization": da,
            "ebit": ebit,
            # yfinance's own sign convention for these three varies by
            # issuer (an expense is sometimes reported negative) -- this
            # schema, like the hand-entered data, always wants a positive
            # magnitude.
            "interest_expense": abs(interest_expense_raw) if interest_expense_raw is not None else None,
            "tax_expense": abs(tax_expense_raw) if tax_expense_raw is not None else None,
            "net_profit": _first_available(income, _INCOME_FIELDS["net_profit"], ic),
            "total_assets": _first_available(balance, _BALANCE_FIELDS["total_assets"], bc),
            "total_debt": _first_available(balance, _BALANCE_FIELDS["total_debt"], bc),
            "cash_and_equivalents": _first_available(cashflow, _CASHFLOW_FIELDS["cash_and_equivalents"], cc),
            "net_working_capital": _first_available(balance, _BALANCE_FIELDS["net_working_capital"], bc),
            "capex": abs(capex_raw) if capex_raw is not None else None,
            "shares_outstanding": _first_available(balance, _BALANCE_FIELDS["shares_outstanding"], bc),
        }
        if any(v is None for v in values.values()):
            # An incomplete fiscal year (common for the most recent,
            # still-reporting one) -- skip it rather than feed a PENDING-like
            # gap downstream; financials.py's own schema has no placeholder
            # for "missing from yfinance".
            continue

        row = {"fiscal_year": _fiscal_year_label(ic)}
        for key, value in values.items():
            # shares_outstanding is a share count, not a currency amount --
            # every other field converts from yfinance's raw rupees to the
            # schema's lakh convention (reverse_dcf.forward.LAKH_TO_RUPEES).
            row[key] = value if key == "shares_outstanding" else value / LAKH
        rows.append(row)

    if len(rows) < MIN_FISCAL_YEARS:
        raise ValueError(
            f"only {len(rows)} complete fiscal year(s) of yfinance data for {ticker!r} "
            f"(need at least {MIN_FISCAL_YEARS} to derive a year-over-year reinvestment rate)"
        )
    return pd.DataFrame(rows, columns=REQUIRED_COLUMNS)


def write_live_financials_csv(ticker: str, out_path: str | Path) -> Path:
    """Fetch ``ticker``'s yfinance financials and write them to ``out_path``
    in the same CSV shape ``reverse_dcf.financials.load_financials`` reads.
    """
    df = fetch_yfinance_financials(ticker)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    return out_path
