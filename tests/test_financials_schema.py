from pathlib import Path

import pytest

from reverse_dcf.financials import (
    LINE_ITEM_COLUMNS,
    REQUIRED_COLUMNS,
    find_pending,
    load_financials,
)

DATA = Path(__file__).resolve().parent.parent / "data" / "GULFOILLUB" / "financials.csv"

EXPECTED_FISCAL_YEARS = [f"FY{y}-{str(y + 1)[2:]}" for y in range(2014, 2024)]


def test_schema_has_required_columns():
    df = load_financials(DATA)
    assert list(df.columns) == REQUIRED_COLUMNS


def test_schema_covers_ten_fiscal_years_in_order():
    df = load_financials(DATA)
    assert df["fiscal_year"].tolist() == EXPECTED_FISCAL_YEARS


def test_missing_column_raises(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("fiscal_year,revenue\nFY2014-15,100\n")
    with pytest.raises(ValueError):
        load_financials(bad)


def test_committed_financials_are_still_all_pending():
    # Day 2 is blocked on sourcing (see research/sources.md) - no real figures
    # have been entered yet, only the schema. This test documents that honest
    # state and should start failing, cell by cell, as real data lands.
    df = load_financials(DATA)
    pending = find_pending(df)
    assert len(pending) == len(EXPECTED_FISCAL_YEARS) * len(LINE_ITEM_COLUMNS)
