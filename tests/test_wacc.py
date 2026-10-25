import math

import pytest

from reverse_dcf.financials import REQUIRED_COLUMNS
from reverse_dcf.wacc import (
    DEFAULT_FINANCIALS,
    CostOfDebt,
    capital_structure,
    compute_wacc,
    cost_of_equity,
    effective_tax_rate,
    load_india_erp,
    load_industry_beta,
    load_risk_free_rate,
    relever_beta,
)

_HEADER = ",".join(REQUIRED_COLUMNS)

# V10: a debt-free issuer (not rare on NSE -- several F&O large caps carry
# no debt). interest_expense and total_debt are both 0 in every year, so
# CostOfDebt.pretax's average_total_debt denominator is exactly 0.
_ZERO_DEBT_FINANCIALS = (
    _HEADER + "\n"
    "FY2022-23,1000,200,20,180,0,45,135,1000,0,100,50,30,100\n"
    "FY2023-24,1100,220,22,198,0,49.5,148.5,1100,0,110,55,33,100\n"
)

# V11: a leveraged, loss-making issuer whose total_debt exceeds total_assets
# -- book equity (total_assets - total_debt) is negative, the same shape as
# the critique's own reproduction.
_NEGATIVE_BOOK_EQUITY_FINANCIALS = (
    _HEADER + "\n"
    "FY2022-23,500,-40,10,-50,40,0,-90,800,900,20,10,5,50\n"
    "FY2023-24,480,-60,10,-70,45,0,-115,750,950,15,8,4,50\n"
)


def test_load_india_erp_matches_damodaran_fixture():
    assert load_india_erp() == pytest.approx(0.0708)


def test_load_risk_free_rate_matches_latest_fred_observation():
    assert load_risk_free_rate() == pytest.approx(0.0706)


def test_load_industry_beta_is_gulf_oils_damodaran_classification():
    industry = load_industry_beta()
    assert industry["industry_name"] == "Chemical (Basic)"
    assert industry["unlevered_beta"] == pytest.approx(0.715283, rel=1e-4)


def test_relever_beta_exceeds_unlevered_beta_for_a_levered_company():
    # Any positive D/E raises the levered beta above the unlevered one -
    # debt adds risk to the equity claim.
    levered = relever_beta(unlevered_beta=0.7, tax_rate=0.25, de_ratio=0.2)
    assert levered > 0.7


def test_relever_beta_equals_unlevered_beta_at_zero_leverage():
    assert relever_beta(unlevered_beta=0.7, tax_rate=0.25, de_ratio=0.0) == pytest.approx(0.7)


def test_cost_of_equity_is_capm():
    assert cost_of_equity(risk_free_rate=0.07, beta=1.2, equity_risk_premium=0.08) == pytest.approx(
        0.07 + 1.2 * 0.08
    )


def test_effective_tax_rate_from_ebit_identity():
    # ebit=100, interest=10 -> pretax income=90; tax=22.5 -> 25%.
    assert effective_tax_rate(ebit=100, interest_expense=10, tax_expense=22.5) == pytest.approx(0.25)


def test_cost_of_debt_after_tax_is_lower_than_pretax():
    debt = CostOfDebt(interest_expense=100, average_total_debt=1000, tax_rate=0.25)
    assert debt.pretax == pytest.approx(0.10)
    assert debt.after_tax == pytest.approx(0.075)
    assert debt.after_tax < debt.pretax


def test_capital_structure_weights_sum_to_one():
    # book_equity = total_assets - total_debt = 700; total_capital = debt + book_equity = 1000.
    weight_debt, weight_equity = capital_structure(total_debt=300, total_assets=1000)
    assert weight_debt == pytest.approx(300 / 1000)
    assert weight_equity == pytest.approx(700 / 1000)
    assert weight_debt + weight_equity == pytest.approx(1.0)


def test_capital_structure_requires_positive_book_equity():
    # total_debt >= total_assets would divide by zero or go negative - not a
    # case the Gulf Oil data hits, but the function shouldn't silently
    # produce a nonsensical negative equity weight.
    weight_debt, weight_equity = capital_structure(total_debt=100, total_assets=1000)
    assert 0 < weight_debt < 1
    assert 0 < weight_equity < 1


def test_compute_wacc_defaults_to_most_recent_fiscal_year():
    result = compute_wacc(DEFAULT_FINANCIALS)
    assert result.fiscal_year == "FY2023-24"


def test_compute_wacc_rejects_the_first_fiscal_year():
    # No prior year exists to average total_debt against.
    with pytest.raises(ValueError):
        compute_wacc(DEFAULT_FINANCIALS, fiscal_year="FY2014-15")


def test_compute_wacc_rejects_unknown_fiscal_year():
    with pytest.raises(ValueError):
        compute_wacc(DEFAULT_FINANCIALS, fiscal_year="FY1999-00")


def test_compute_wacc_is_a_plausible_rate_for_an_indian_industrial_mid_cap():
    # Not a precision check - a bound against a sign error, a units slip
    # (percent vs. decimal), or a formula regression producing something
    # absurd like a negative or 300% WACC.
    result = compute_wacc(DEFAULT_FINANCIALS)
    assert 0.08 < result.wacc < 0.18
    assert result.wacc > result.cost_of_debt_after_tax
    assert result.wacc < result.cost_of_equity


def test_compute_wacc_weights_sum_to_one():
    result = compute_wacc(DEFAULT_FINANCIALS)
    assert result.weight_debt + result.weight_equity == pytest.approx(1.0)


def test_assumptions_block_names_every_component():
    result = compute_wacc(DEFAULT_FINANCIALS)
    block = result.assumptions_block()
    for label in ("Risk-free rate", "equity risk premium", "unlevered beta", "Cost of equity", "Cost of debt", "WACC"):
        assert label in block


def test_wacc_round_trips_through_its_own_formula():
    # The WACC formula itself, not the data pipeline: given the components
    # compute_wacc derived, the weighted blend must equal the reported WACC.
    result = compute_wacc(DEFAULT_FINANCIALS)
    recomputed = result.weight_equity * result.cost_of_equity + result.weight_debt * result.cost_of_debt_after_tax
    assert recomputed == pytest.approx(result.wacc)
    assert not math.isnan(result.wacc)


def test_compute_wacc_matches_the_pinned_gulfoillub_value():
    # V10/V11 (CRITIQUES.md): the zero-debt and negative-book-equity guards
    # added below must not move GULFOILLUB's own real WACC (positive debt,
    # positive book equity) at all -- pinned byte-identical to the value
    # computed before those guards existed. Re-pinned on Day 101 (D29) to the
    # 2026-10-25 WACC fixtures (risk-free 6.89% -> 7.06%).
    result = compute_wacc(DEFAULT_FINANCIALS)
    assert result.wacc == pytest.approx(0.11756184381039692, rel=1e-12)


# --- V10: zero-debt issuer --------------------------------------------------


def test_cost_of_debt_is_zero_not_nan_for_an_all_equity_issuer():
    debt = CostOfDebt(interest_expense=0.0, average_total_debt=0.0, tax_rate=0.25)
    assert debt.pretax == 0.0
    assert debt.after_tax == 0.0
    assert not math.isnan(debt.pretax)
    assert not math.isnan(debt.after_tax)


def test_compute_wacc_is_finite_and_equals_cost_of_equity_for_a_zero_debt_ticker(tmp_path):
    path = tmp_path / "zero_debt.csv"
    path.write_text(_ZERO_DEBT_FINANCIALS)
    result = compute_wacc(path)
    assert not math.isnan(result.wacc)
    assert result.weight_debt == 0.0
    assert result.cost_of_debt_after_tax == 0.0
    # An all-equity firm's WACC is just its cost of equity.
    assert result.wacc == pytest.approx(result.cost_of_equity)


# --- V11: negative book equity ----------------------------------------------


def test_capital_structure_raises_on_negative_book_equity():
    # total_debt (900) exceeds total_assets (800) -- book_equity is negative,
    # which used to silently produce weight_debt > 1 and weight_equity < 0.
    with pytest.raises(ValueError, match="book equity"):
        capital_structure(total_debt=900, total_assets=800, ticker="DISTRESSEDCO")


def test_effective_tax_rate_raises_on_nonpositive_pretax_income():
    # ebit=-70, interest_expense=45 -> pretax_income=-115: not a meaningful
    # "effective tax rate" base, and the sign flip used to cascade silently
    # into a negative relevered beta and cost of equity.
    with pytest.raises(ValueError, match="pretax income"):
        effective_tax_rate(ebit=-70, interest_expense=45, tax_expense=0, ticker="DISTRESSEDCO")


def test_compute_wacc_raises_clearly_for_a_negative_book_equity_ticker(tmp_path):
    path = tmp_path / "negative_book_equity.csv"
    path.write_text(_NEGATIVE_BOOK_EQUITY_FINANCIALS)
    with pytest.raises(ValueError, match="DISTRESSEDCO"):
        compute_wacc(path, ticker="DISTRESSEDCO")
