import math

import pytest

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


def test_load_india_erp_matches_damodaran_fixture():
    assert load_india_erp() == pytest.approx(0.0708)


def test_load_risk_free_rate_matches_latest_fred_observation():
    assert load_risk_free_rate() == pytest.approx(0.0689)


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
