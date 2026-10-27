"""V26 (CRITIQUES.md): optional treasury columns outside cash equivalents."""

import math

import pandas as pd
import pytest

from reverse_dcf.financials import OPTIONAL_COLUMNS, load_financials, to_numeric
from reverse_dcf.forward import (
    DEFAULT_FINANCIALS,
    LAKH_TO_RUPEES,
    base_case_from_financials,
    invested_capital,
    non_operating_liquid_assets,
)


def _with_treasury(tmp_path, other_bank_balances, current_investments):
    df = pd.read_csv(DEFAULT_FINANCIALS, dtype=str)
    df["other_bank_balances"] = ""
    df["current_investments"] = ""
    df.loc[df.index[-1], "other_bank_balances"] = other_bank_balances
    df.loc[df.index[-1], "current_investments"] = current_investments
    path = tmp_path / "financials.csv"
    df.to_csv(path, index=False)
    return path


def test_optional_columns_are_named():
    assert OPTIONAL_COLUMNS == ["other_bank_balances", "current_investments"]


def test_committed_fixture_has_no_treasury_columns_so_nothing_changes():
    row = to_numeric(load_financials(DEFAULT_FINANCIALS)).iloc[-1]
    assert non_operating_liquid_assets(row) == 0.0
    assert invested_capital(row) == row["total_assets"] - row["cash_and_equivalents"]


def test_blank_treasury_cells_load_as_nan_and_count_as_zero(tmp_path):
    path = _with_treasury(tmp_path, "", "")
    df = to_numeric(load_financials(path))
    assert math.isnan(df["other_bank_balances"].iloc[-1])
    assert non_operating_liquid_assets(df.iloc[-1]) == 0.0
    assert base_case_from_financials(path, revenue_growth=0.05).net_debt == pytest.approx(
        base_case_from_financials(DEFAULT_FINANCIALS, revenue_growth=0.05).net_debt
    )


def test_transcribed_treasury_lowers_net_debt_and_invested_capital(tmp_path):
    path = _with_treasury(tmp_path, "500", "233")
    row = to_numeric(load_financials(path)).iloc[-1]
    assert non_operating_liquid_assets(row) == 733.0
    assert invested_capital(row) == row["total_assets"] - row["cash_and_equivalents"] - 733.0
    before = base_case_from_financials(DEFAULT_FINANCIALS, revenue_growth=0.05).net_debt
    after = base_case_from_financials(path, revenue_growth=0.05).net_debt
    assert before - after == pytest.approx(733.0 * LAKH_TO_RUPEES)


def test_non_numeric_treasury_cell_raises(tmp_path):
    path = _with_treasury(tmp_path, "abc", "")
    with pytest.raises(ValueError, match="other_bank_balances"):
        to_numeric(load_financials(path))
