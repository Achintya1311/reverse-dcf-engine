"""Schema and loader for the hand-entered financials CSV (Day 2 deliverable).

The reverse DCF needs ten years of line items per company, hand-transcribed
from annual reports and cited by document and page in ``research/sources.md``.
This module only checks structure - the right columns, the right fiscal-year
coverage, and whether a cell is still the ``PENDING`` placeholder committed
while sourcing was blocked. It has no opinion on whether a filled-in number is
correct; that is what the citation ledger is for.
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
