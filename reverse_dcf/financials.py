"""Schema, loader and validation for the hand-entered financials CSV (Day 2).

The reverse DCF needs ten years of line items per company, hand-transcribed
from annual reports and cited by document and page in ``research/sources.md``.
Every figure here is the audited number as reported, or a small derivation of
audited numbers using a fixed, documented rule (see ``research/sources.md``'s
methodology section):

- ``ebit`` = Profit before tax + Finance costs (interest expense added back).
- ``ebitda`` = ``ebit`` + depreciation and amortisation.
- ``net_working_capital`` = (total current assets - cash and equivalents -
  other bank balances) - (total current liabilities - total debt).
- ``cash_and_equivalents`` is the Cash Flow Statement's ending balance, not
  the (sometimes broader) Balance Sheet line, so the definition is consistent
  across the pre- and post-Ind AS reporting formats this company used over
  the ten years.

This module checks structure (the right columns, the right fiscal-year
coverage), whether a cell is still the ``PENDING`` placeholder used while
sourcing was blocked, and the one internal identity the derivation above
implies (``ebitda - depreciation_amortization == ebit``). It has no way to
check a transcribed number against the source PDF itself; that is what the
citation ledger in ``research/sources.md`` is for.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

PENDING = "PENDING"

REQUIRED_COLUMNS = [
    "fiscal_year",
    "revenue",
    "ebitda",
    "depreciation_amortization",
    "ebit",
    "interest_expense",
    "tax_expense",
    "net_profit",
    "total_assets",
    "total_debt",
    "cash_and_equivalents",
    "net_working_capital",
    "capex",
    "shares_outstanding",
]

LINE_ITEM_COLUMNS = REQUIRED_COLUMNS[1:]


def load_financials(path: str | Path) -> pd.DataFrame:
    """Load the financials CSV and validate it against the Day 2 schema.

    Raises ``ValueError`` if a required column is missing. Does not raise on
    ``PENDING`` cells - use :func:`find_pending` to check for those.
    """
    df = pd.read_csv(path, dtype=str)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"financials.csv missing columns: {missing}")
    return df


def find_pending(df: pd.DataFrame) -> list[tuple[str, str]]:
    """Return (fiscal_year, column) pairs still holding the PENDING placeholder."""
    return [
        (row["fiscal_year"], col)
        for _, row in df.iterrows()
        for col in LINE_ITEM_COLUMNS
        if row[col] == PENDING
    ]


def to_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with every line-item column coerced to ``float``.

    Raises ``ValueError`` (naming the offending fiscal year and column) if a
    cell is not a plain number - a ``PENDING`` placeholder included, so this
    is also a stricter check than :func:`find_pending`: it catches any other
    non-numeric junk a transcription slip might introduce.
    """
    out = df.copy()
    for col in LINE_ITEM_COLUMNS:
        try:
            out[col] = out[col].astype(float)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"non-numeric values in column '{col}': {exc}") from exc
    return out


def check_ebit_identity(df: pd.DataFrame, tolerance: float = 0.05) -> list[str]:
    """Return fiscal years where ``ebitda - depreciation_amortization != ebit``.

    Both figures are derived from the same two reported numbers (profit
    before tax and finance costs) via a different path, so they must agree
    to within rounding. A mismatch means a transcription or arithmetic slip
    in one of the two columns, not a real accounting fact.
    """
    numeric = to_numeric(df)
    mismatches = []
    for _, row in numeric.iterrows():
        implied_ebit = row["ebitda"] - row["depreciation_amortization"]
        if abs(implied_ebit - row["ebit"]) > tolerance:
            mismatches.append(row["fiscal_year"])
    return mismatches
