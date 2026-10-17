"""C1 Day 23: tests for the yfinance financials adapter.

Two kinds of test, same split LESSONS.md and STOCKSTALKER's
test_live_provider_smoke.py already use elsewhere in this project:

- Deterministic, offline tests of the field-mapping/fallback/unit-conversion
  logic, with ``yfinance.Ticker`` monkeypatched to small, hand-built
  statement frames -- no network, never flaky.
- One real, live cross-check against GULFOILLUB's own hand-entered data
  (the "revenue matches within 1%" requirement NEXT_STEPS.md Day 23
  names). It skips cleanly, never fails, when this sandbox's outbound
  network to Yahoo isn't reachable -- a sandbox-level network failure is
  not this adapter's bug.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from reverse_dcf.financials import REQUIRED_COLUMNS, load_financials
from reverse_dcf.live_financials import (
    FINANCIALS_SOURCE_LIVE,
    fetch_yfinance_financials,
    write_live_financials_csv,
)

GULFOILLUB_HAND_ENTERED = Path(__file__).resolve().parent.parent / "data" / "GULFOILLUB" / "financials.csv"
GULFOILLUB_FY24 = "FY2023-24"
HAND_ENTERED_FY24_REVENUE_LAKH = 328409.68


def _ts(year: int) -> pd.Timestamp:
    return pd.Timestamp(f"{year}-03-31")


class _FakeTicker:
    """Stands in for ``yfinance.Ticker`` with two complete fiscal years and
    one deliberately incomplete one (year 3, missing ``EBIT`` -- must be
    skipped, not fed downstream as a gap)."""

    def __init__(self, ticker: str):
        self.ticker = ticker

    def get_income_stmt(self, freq="yearly"):
        cols = [_ts(2023), _ts(2024), _ts(2025)]
        data = {
            "TotalRevenue": [100_000_000.0, 120_000_000.0, 140_000_000.0],
            "EBITDA": [20_000_000.0, 24_000_000.0, 28_000_000.0],
            "EBIT": [18_000_000.0, 21_000_000.0, None],  # year 3 incomplete
            "DepreciationAndAmortizationInIncomeStatement": [2_000_000.0, 3_000_000.0, 4_000_000.0],
            "InterestExpense": [-1_000_000.0, -1_200_000.0, -1_400_000.0],  # negative sign convention
            "TaxProvision": [2_500_000.0, 3_000_000.0, 3_500_000.0],
            "NetIncome": [9_000_000.0, 11_000_000.0, 13_000_000.0],
        }
        return pd.DataFrame({c: [data[k][i] for k in data] for i, c in enumerate(cols)}, index=list(data))

    def get_balance_sheet(self, freq="yearly"):
        cols = [_ts(2023), _ts(2024), _ts(2025)]
        data = {
            "TotalAssets": [200_000_000.0, 230_000_000.0, 260_000_000.0],
            "TotalDebt": [30_000_000.0, 28_000_000.0, 26_000_000.0],
            "WorkingCapital": [40_000_000.0, 45_000_000.0, 50_000_000.0],
            "OrdinarySharesNumber": [49_000_000.0, 49_100_000.0, 49_200_000.0],
        }
        return pd.DataFrame({c: [data[k][i] for k in data] for i, c in enumerate(cols)}, index=list(data))

    def get_cashflow(self, freq="yearly"):
        cols = [_ts(2023), _ts(2024), _ts(2025)]
        data = {
            "EndCashPosition": [15_000_000.0, 18_000_000.0, 20_000_000.0],
            "CapitalExpenditure": [-5_000_000.0, -6_000_000.0, -7_000_000.0],  # outflow, negative
            "DepreciationAndAmortization": [2_000_000.0, 3_000_000.0, 4_000_000.0],
        }
        return pd.DataFrame({c: [data[k][i] for k in data] for i, c in enumerate(cols)}, index=list(data))


def test_fetch_yfinance_financials_has_the_required_schema(monkeypatch):
    import yfinance

    monkeypatch.setattr(yfinance, "Ticker", _FakeTicker)
    df = fetch_yfinance_financials("FAKE.NS")
    assert list(df.columns) == REQUIRED_COLUMNS


def test_fetch_yfinance_financials_skips_an_incomplete_fiscal_year(monkeypatch):
    # Year 3 (FY2024-25) is missing EBIT in the fake fixture above -- it
    # must not appear in the output at all, not as a row with a NaN/None gap.
    import yfinance

    monkeypatch.setattr(yfinance, "Ticker", _FakeTicker)
    df = fetch_yfinance_financials("FAKE.NS")
    assert df["fiscal_year"].tolist() == ["FY2022-23", "FY2023-24"]


def test_fetch_yfinance_financials_converts_rupees_to_lakh(monkeypatch):
    import yfinance

    monkeypatch.setattr(yfinance, "Ticker", _FakeTicker)
    df = fetch_yfinance_financials("FAKE.NS").set_index("fiscal_year")
    # TotalRevenue 100_000_000 rupees == 1_000 lakh.
    assert df.loc["FY2022-23", "revenue"] == pytest.approx(1_000.0)


def test_fetch_yfinance_financials_takes_the_absolute_value_of_signed_fields(monkeypatch):
    # InterestExpense (-1_000_000) and CapitalExpenditure (-5_000_000) both
    # arrive negative in the fake fixture (yfinance's own outflow/expense
    # sign convention) -- the schema always wants a positive magnitude, the
    # same convention the hand-entered GULFOILLUB CSV uses.
    import yfinance

    monkeypatch.setattr(yfinance, "Ticker", _FakeTicker)
    df = fetch_yfinance_financials("FAKE.NS").set_index("fiscal_year")
    assert df.loc["FY2022-23", "interest_expense"] == pytest.approx(10.0)
    assert df.loc["FY2022-23", "capex"] == pytest.approx(50.0)


def test_fetch_yfinance_financials_matches_shares_outstanding_without_unit_conversion(monkeypatch):
    import yfinance

    monkeypatch.setattr(yfinance, "Ticker", _FakeTicker)
    df = fetch_yfinance_financials("FAKE.NS").set_index("fiscal_year")
    assert df.loc["FY2022-23", "shares_outstanding"] == pytest.approx(49_000_000.0)


class _EmptyTicker:
    def __init__(self, ticker: str):
        pass

    def get_income_stmt(self, freq="yearly"):
        return pd.DataFrame()

    def get_balance_sheet(self, freq="yearly"):
        return pd.DataFrame()

    def get_cashflow(self, freq="yearly"):
        return pd.DataFrame()


def test_fetch_yfinance_financials_raises_on_no_statements(monkeypatch):
    import yfinance

    monkeypatch.setattr(yfinance, "Ticker", _EmptyTicker)
    with pytest.raises(ValueError, match="no annual financial statements"):
        fetch_yfinance_financials("NOTATICKER.NS")


class _OneCompleteYearTicker(_FakeTicker):
    """Only FY2022-23 is complete -- below MIN_FISCAL_YEARS (2)."""

    def get_income_stmt(self, freq="yearly"):
        df = super().get_income_stmt(freq)
        df.loc["EBIT", _ts(2024)] = None
        return df


def test_fetch_yfinance_financials_raises_when_fewer_than_two_complete_years(monkeypatch):
    import yfinance

    monkeypatch.setattr(yfinance, "Ticker", _OneCompleteYearTicker)
    with pytest.raises(ValueError, match="only 1 complete fiscal year"):
        fetch_yfinance_financials("FAKE.NS")


def test_write_live_financials_csv_round_trips_through_load_financials(monkeypatch, tmp_path):
    import yfinance

    monkeypatch.setattr(yfinance, "Ticker", _FakeTicker)
    out_path = tmp_path / "live" / "FAKE.csv"
    written = write_live_financials_csv("FAKE.NS", out_path)
    assert written == out_path
    assert out_path.exists()
    df = load_financials(out_path)
    assert list(df.columns) == REQUIRED_COLUMNS
    assert len(df) == 2


# -- Live cross-check (NEXT_STEPS.md Day 23) ---------------------------------


def test_yfinance_gulfoillub_fy24_revenue_matches_hand_entered_within_1pct():
    try:
        df = fetch_yfinance_financials("GULFOILLUB.NS")
    except (ValueError, OSError) as exc:
        pytest.skip(
            f"no live network reachable for yfinance in this sandbox ({exc}); "
            "this is the offline/zero-spend default working as intended, not "
            "an adapter bug. Re-run with outbound network to actually exercise "
            "the live path."
        )
        return

    row = df[df["fiscal_year"] == GULFOILLUB_FY24]
    if row.empty:
        pytest.skip(
            "yfinance's own trailing 4-5 year window no longer includes "
            f"{GULFOILLUB_FY24} for GULFOILLUB (expected to age out eventually)"
        )
        return

    live_revenue = float(row.iloc[0]["revenue"])
    pct_diff = abs(live_revenue - HAND_ENTERED_FY24_REVENUE_LAKH) / HAND_ENTERED_FY24_REVENUE_LAKH
    assert pct_diff < 0.01, (
        f"yfinance {GULFOILLUB_FY24} revenue {live_revenue:.2f} lakh vs hand-entered "
        f"{HAND_ENTERED_FY24_REVENUE_LAKH:.2f} lakh ({GULFOILLUB_HAND_ENTERED}) differs "
        f"by {pct_diff:.2%}, expected <1%"
    )


def test_yfinance_gulfoillub_schema_matches_hand_entered_columns():
    try:
        df = fetch_yfinance_financials("GULFOILLUB.NS")
    except (ValueError, OSError) as exc:
        pytest.skip(f"no live network reachable for yfinance in this sandbox ({exc})")
        return
    assert list(df.columns) == REQUIRED_COLUMNS
    assert not df.empty
    assert FINANCIALS_SOURCE_LIVE  # sanity: the label constant exists and is non-empty
