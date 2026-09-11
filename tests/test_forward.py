import math

import pandas as pd
import pytest

from reverse_dcf.forward import (
    DEFAULT_FINANCIALS,
    DcfAssumptions,
    base_case_from_financials,
    fcff_from_revenue,
    historical_reinvestment_rate,
    present_value,
    project_fcff,
    project_revenue,
    run_dcf,
    terminal_value,
)
from reverse_dcf.financials import load_financials, to_numeric
from reverse_dcf.wacc import compute_wacc, load_risk_free_rate


def test_project_revenue_compounds_at_a_constant_rate():
    revenues = project_revenue(revenue_base=100.0, growth_rate=0.10, years=3)
    assert revenues == [pytest.approx(110.0), pytest.approx(121.0), pytest.approx(133.1)]


def test_project_revenue_rejects_zero_years():
    with pytest.raises(ValueError):
        project_revenue(revenue_base=100.0, growth_rate=0.1, years=0)


def test_fcff_from_revenue_is_nopat_less_reinvestment():
    # revenue=1000, margin=20% -> ebit=200; tax=25% -> nopat=150; reinvestment 40% -> fcff=90.
    fcff = fcff_from_revenue(revenue=1000.0, ebit_margin=0.20, tax_rate=0.25, reinvestment_rate=0.40)
    assert fcff == pytest.approx(90.0)


def test_project_fcff_applies_same_assumptions_to_every_year():
    revenues = [1000.0, 1100.0]
    fcffs = project_fcff(revenues, ebit_margin=0.20, tax_rate=0.25, reinvestment_rate=0.40)
    assert fcffs[0] == pytest.approx(90.0)
    assert fcffs[1] == pytest.approx(fcff_from_revenue(1100.0, 0.20, 0.25, 0.40))


def test_present_value_matches_manual_discounting():
    cashflows = [100.0, 100.0]
    wacc = 0.10
    expected = 100.0 / 1.10 + 100.0 / 1.10**2
    assert present_value(cashflows, wacc) == pytest.approx(expected)


def test_terminal_value_is_gordon_growth_on_the_year_after_the_last_forecast():
    tv = terminal_value(final_year_fcff=100.0, wacc=0.12, terminal_growth=0.04)
    assert tv == pytest.approx(100.0 * 1.04 / (0.12 - 0.04))


def test_terminal_value_rejects_growth_at_or_above_wacc():
    with pytest.raises(ValueError):
        terminal_value(final_year_fcff=100.0, wacc=0.08, terminal_growth=0.08)
    with pytest.raises(ValueError):
        terminal_value(final_year_fcff=100.0, wacc=0.08, terminal_growth=0.09)


def _perpetuity_assumptions(forecast_years: int, g: float = 0.05) -> DcfAssumptions:
    return DcfAssumptions(
        revenue_base=1000.0,
        revenue_growth=g,
        ebit_margin=0.20,
        tax_rate=0.25,
        reinvestment_rate=0.30,
        wacc=0.11,
        terminal_growth=g,
        forecast_years=forecast_years,
        net_debt=200.0,
        shares_outstanding=100.0,
    )


def test_enterprise_value_matches_a_growing_perpetuity_when_growth_equals_terminal_growth():
    # When the explicit-period growth rate and the terminal growth rate are
    # the same, the whole forecast is one constant-growth stream. Splitting
    # a growing perpetuity into "n explicit years + a terminal value" is an
    # accounting convenience, not a different model - the total present
    # value must be independent of where the split falls (n=1 vs n=10), and
    # must equal the textbook single-stage Gordon growth value discounted
    # from t=1. This is the closest a forward-only Day 4 engine can get to
    # the round-trip check Day 5's reverse solver will run for real.
    a = _perpetuity_assumptions(forecast_years=1)
    fcff_1 = fcff_from_revenue(
        a.revenue_base * (1 + a.revenue_growth), a.ebit_margin, a.tax_rate, a.reinvestment_rate
    )
    closed_form_ev = fcff_1 / (a.wacc - a.terminal_growth)

    result_n1 = run_dcf(_perpetuity_assumptions(forecast_years=1))
    result_n10 = run_dcf(_perpetuity_assumptions(forecast_years=10))

    assert result_n1.enterprise_value == pytest.approx(closed_form_ev, rel=1e-9)
    assert result_n10.enterprise_value == pytest.approx(closed_form_ev, rel=1e-6)


def test_run_dcf_equity_value_and_share_price_arithmetic():
    result = run_dcf(_perpetuity_assumptions(forecast_years=5))
    assert result.equity_value == pytest.approx(result.enterprise_value - 200.0)
    assert result.implied_share_price == pytest.approx(result.equity_value / 100.0)


def test_run_dcf_higher_growth_raises_the_implied_price_all_else_equal():
    low = run_dcf(_perpetuity_assumptions(forecast_years=5, g=0.03))
    high = run_dcf(_perpetuity_assumptions(forecast_years=5, g=0.06))
    assert high.implied_share_price > low.implied_share_price


def test_historical_reinvestment_rate_formula():
    current = pd.Series({"ebit": 200.0, "capex": 80.0, "depreciation_amortization": 20.0, "net_working_capital": 150.0})
    prior = pd.Series({"net_working_capital": 130.0})
    # nopat = 200*(1-0.25) = 150; reinvestment = 80 - 20 + (150-130) = 80; rate = 80/150.
    rate = historical_reinvestment_rate(current, prior, tax_rate=0.25)
    assert rate == pytest.approx(80.0 / 150.0)


def test_base_case_from_financials_uses_days_2_and_3_outputs_not_new_numbers():
    assumptions = base_case_from_financials(DEFAULT_FINANCIALS, revenue_growth=0.10)
    wacc_result = compute_wacc(DEFAULT_FINANCIALS)
    assert assumptions.wacc == pytest.approx(wacc_result.wacc)
    assert assumptions.terminal_growth == pytest.approx(load_risk_free_rate())
    assert 0 < assumptions.ebit_margin < 1
    assert assumptions.wacc > assumptions.terminal_growth
    assert assumptions.shares_outstanding > 0


def test_base_case_from_financials_terminal_growth_override():
    assumptions = base_case_from_financials(DEFAULT_FINANCIALS, revenue_growth=0.10, terminal_growth=0.03)
    assert assumptions.terminal_growth == pytest.approx(0.03)


def test_run_dcf_on_gulf_oils_actual_base_case_is_a_plausible_price():
    # Not a precision check on the valuation itself - Day 5 owns solving for
    # a growth rate the market would actually be pricing in. This just
    # guards against a sign error or a units slip (lakh vs. crore, percent
    # vs. decimal) producing a negative or absurd implied price.
    assumptions = base_case_from_financials(DEFAULT_FINANCIALS, revenue_growth=0.10, forecast_years=10)
    result = run_dcf(assumptions)
    assert result.enterprise_value > 0
    assert not math.isnan(result.implied_share_price)
    # Gulf Oil's Day 1 shortlist put its market cap at ~5,600-5,800 cr against
    # ~49.17m shares, i.e. an actual price in the low thousands of rupees. A
    # price outside two orders of magnitude of that is a units bug (e.g. the
    # financials.csv-is-in-lakh conversion silently dropped), not a bold
    # valuation - lakh-per-share instead of rupees-per-share was exactly the
    # bug this bound catches.
    assert 10 < result.implied_share_price < 100_000


def test_base_case_converts_financials_csv_lakh_to_rupees():
    # data/GULFOILLUB/financials.csv is denominated in lakh (see the module
    # docstring's LAKH_TO_RUPEES note) - revenue_base and net_debt must come
    # out of base_case_from_financials already converted to rupees, since
    # shares_outstanding is a raw share count, not a lakh figure.
    from reverse_dcf.forward import LAKH_TO_RUPEES

    df = to_numeric(load_financials(DEFAULT_FINANCIALS)).set_index("fiscal_year")
    latest = df.iloc[-1]
    assumptions = base_case_from_financials(DEFAULT_FINANCIALS, revenue_growth=0.10)
    assert assumptions.revenue_base == pytest.approx(latest["revenue"] * LAKH_TO_RUPEES)


def test_dcf_assumptions_override_forwarded_by_cli_main(monkeypatch, capsys):
    import sys

    from reverse_dcf.forward import main

    monkeypatch.setattr(sys, "argv", ["forward.py", "--growth", "0.10", "--years", "5"])
    main()
    out = capsys.readouterr().out
    assert "Implied share price" in out
    assert "Forward FCFF DCF -- 5-year forecast" in out


def test_cli_requires_growth_argument():
    import sys

    from reverse_dcf.forward import main

    argv_backup = sys.argv
    sys.argv = ["forward.py"]
    try:
        with pytest.raises(SystemExit):
            main()
    finally:
        sys.argv = argv_backup
