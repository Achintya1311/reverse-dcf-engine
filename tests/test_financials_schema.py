from pathlib import Path

import pytest

from reverse_dcf.financials import (
    REQUIRED_COLUMNS,
    check_ebit_identity,
    find_pending,
    load_financials,
    to_numeric,
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


def test_no_pending_cells_remain():
    # Day 2's ten years of Gulf Oil Lubricants India financials are now
    # transcribed from the annual reports (see research/sources.md's
    # citation ledger) - no PENDING placeholders should be left.
    df = load_financials(DATA)
    assert find_pending(df) == []


def test_all_line_items_are_numeric():
    # Guards against a stray non-numeric transcription slip (a stray currency
    # symbol, a footnote marker) that find_pending wouldn't catch.
    to_numeric(load_financials(DATA))  # raises ValueError on any bad cell


def test_ebit_equals_ebitda_minus_depreciation():
    # ebit and ebitda are both derived from (profit before tax + finance
    # costs) by a different path - see the financials.py module docstring -
    # so they must agree exactly (within rounding) or one was mistranscribed.
    df = load_financials(DATA)
    assert check_ebit_identity(df) == []


def test_shares_outstanding_are_positive_integers():
    df = to_numeric(load_financials(DATA))
    shares = df["shares_outstanding"]
    assert (shares > 0).all()
    assert (shares == shares.astype(int)).all()
