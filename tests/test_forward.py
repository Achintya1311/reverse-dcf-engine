import math

import pandas as pd
import pytest

from reverse_dcf.forward import (
    DEFAULT_FINANCIALS,
    DcfAssumptions,
    base_case_from_financials,
    check_growth_reinvestment_consistency,
    fcff_from_revenue,
    historical_median_roic,
    historical_reinvestment_rate,
    historical_roic,
    invested_capital,
    is_working_capital_release_year,
    present_value,
    project_fcff,
    project_revenue,
    reinvestment_schedule_from_growth,
    roic_fade_schedule,
    run_dcf,
    terminal_roic,
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


def test_terminal_value_is_gordon_growth_on_a_freshly_built_terminal_year():
    # V6 (CRITIQUES.md, Day 18): terminal_value no longer takes the last
    # explicit year's own FCFF and extrapolates it -- it takes that year's
    # NOPAT (pre-reinvestment) and builds the terminal year itself, grown at
    # terminal_growth and reinvested at terminal_reinvestment_rate.
    tv = terminal_value(final_year_nopat=100.0, wacc=0.12, terminal_growth=0.04, terminal_reinvestment_rate=0.3)
    next_year_fcff = 100.0 * 1.04 * (1 - 0.3)
    assert tv == pytest.approx(next_year_fcff / (0.12 - 0.04))


def test_terminal_value_matches_the_old_extrapolation_when_terminal_reinvestment_rate_equals_the_explicit_rate():
    # The Day-18 formula is a strict generalisation, not a different one: when
    # the terminal year's own rate happens to equal the rate that produced
    # final_year_nopat's own FCFF (no deceleration at the boundary), the new
    # "fresh terminal year" computation and the pre-Day-18 "extrapolate the
    # last year's FCFF" computation must agree exactly.
    final_year_nopat = 100.0
    reinvestment_rate = 0.3
    final_year_fcff = final_year_nopat * (1 - reinvestment_rate)
    old_style_tv = final_year_fcff * 1.04 / (0.12 - 0.04)  # the pre-Day-18 formula, by hand
    new_tv = terminal_value(final_year_nopat, wacc=0.12, terminal_growth=0.04, terminal_reinvestment_rate=reinvestment_rate)
    assert new_tv == pytest.approx(old_style_tv)


def test_terminal_value_rejects_growth_at_or_above_wacc():
    with pytest.raises(ValueError):
        terminal_value(final_year_nopat=100.0, wacc=0.08, terminal_growth=0.08, terminal_reinvestment_rate=0.3)
    with pytest.raises(ValueError):
        terminal_value(final_year_nopat=100.0, wacc=0.08, terminal_growth=0.09, terminal_reinvestment_rate=0.3)


def test_terminal_reinvestment_rate_matches_the_last_explicit_year_when_growth_does_not_decelerate():
    # V6/V7 continuity check (Day 18): when revenue_growth == terminal_growth
    # (no deceleration at the explicit/terminal boundary -- the base case's
    # own ROIC-fade schedule already ends exactly at terminal_roic, see
    # roic_fade_schedule), the schedule's own last explicit-year rate and
    # the new terminal_reinvestment_rate must be the *same number*: the
    # fix changes nothing where there is nothing to fix.
    g = base_case_from_financials(DEFAULT_FINANCIALS, revenue_growth=0.0).terminal_growth
    base = base_case_from_financials(DEFAULT_FINANCIALS, revenue_growth=g, forecast_years=10)
    assert base.terminal_reinvestment_rate == pytest.approx(base.reinvestment_rate[-1])


def test_terminal_reinvestment_rate_differs_from_the_last_explicit_year_when_growth_decelerates():
    # The actual V6 bug: once explicit growth is faster than terminal_growth,
    # the schedule's own last year is reinvested to fund the *explicit* rate,
    # not terminal_growth -- so the two rates are genuinely different
    # numbers, and extrapolating the explicit FCFF (pre-Day-18 behaviour)
    # would silently keep using the wrong one.
    base = base_case_from_financials(DEFAULT_FINANCIALS, revenue_growth=0.08, forecast_years=10)
    assert base.terminal_growth < 0.08
    assert base.terminal_reinvestment_rate != pytest.approx(base.reinvestment_rate[-1])
    # And the terminal rate is always the one consistent with terminal_growth
    # and terminal_roic, regardless of what the explicit growth rate was.
    assert base.terminal_reinvestment_rate == pytest.approx(base.terminal_growth / terminal_roic(base.wacc))


def test_terminal_value_is_continuous_across_the_explicit_terminal_boundary():
    # Day 18's own continuity requirement: nothing about the terminal
    # assumptions changes between year N and year N+1, so pushing the
    # explicit/terminal split out by exactly one year -- one more year's
    # cash flow at the *same* terminal_growth/terminal_reinvestment_rate,
    # discounted back, plus a fresh terminal value computed one year further
    # out at those same inputs -- must reproduce the original terminal
    # value exactly. A terminal formula that silently used a different rate
    # depending on where the boundary happened to fall (the pre-Day-18 bug,
    # for the V2 schedule) would fail this the moment the rate it carries
    # forward differs from the rate consistent with its own growth.
    final_year_nopat = 12345.0
    wacc = 0.12
    terminal_growth = 0.05
    terminal_reinvestment_rate = 0.4

    tv_at_year_n = terminal_value(final_year_nopat, wacc, terminal_growth, terminal_reinvestment_rate)

    next_nopat = final_year_nopat * (1 + terminal_growth)
    next_fcff = next_nopat * (1 - terminal_reinvestment_rate)
    tv_at_year_n_plus_1 = terminal_value(next_nopat, wacc, terminal_growth, terminal_reinvestment_rate)
    tv_via_one_more_year = (next_fcff + tv_at_year_n_plus_1) / (1 + wacc)

    assert tv_via_one_more_year == pytest.approx(tv_at_year_n)


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


def test_invested_capital_is_total_assets_less_cash():
    row = pd.Series({"total_assets": 230449.91, "cash_and_equivalents": 70223.75})
    assert invested_capital(row) == pytest.approx(230449.91 - 70223.75)


def test_historical_roic_uses_beginning_of_year_invested_capital():
    # NOPAT = 200*(1-0.25) = 150; prior-year invested capital = 1000-100 = 900; ROIC = 150/900.
    current = pd.Series({"ebit": 200.0})
    prior = pd.Series({"total_assets": 1000.0, "cash_and_equivalents": 100.0})
    roic = historical_roic(current, prior, tax_rate=0.25)
    assert roic == pytest.approx(150.0 / 900.0)


def test_roic_fade_schedule_rejects_a_fade_that_crosses_zero():
    # V8 (CRITIQUES.md): a median/terminal ROIC pair whose linear fade
    # straddles zero lands one year's ROIC within a few ulps of 0.0 --
    # reinvestment_schedule_from_growth would then divide a nonzero growth
    # rate by that near-zero number, producing an astronomical reinvestment
    # rate (reproduced directly: a -5% -> +10% fade over 10 years lands
    # exactly on 0.0 at year 4) rather than a real one. roic_fade_schedule
    # must refuse to build such a schedule at all, before any division
    # happens downstream.
    with pytest.raises(ValueError, match=r"(?i)roic.*zero|zero.*roic"):
        roic_fade_schedule(median_roic=-0.05, terminal_roic_value=0.10, forecast_years=10)


def test_roic_fade_schedule_error_names_the_ticker_and_year():
    with pytest.raises(ValueError) as exc_info:
        roic_fade_schedule(median_roic=-0.05, terminal_roic_value=0.10, forecast_years=10, ticker="LOSSMAKER")
    message = str(exc_info.value)
    assert "LOSSMAKER" in message
    assert "4" in message  # the fade crosses zero at (0-indexed) year 4


def test_roic_fade_schedule_tolerates_a_fade_that_only_approaches_zero_from_one_side():
    # Not every low ROIC is a crossing: a fade that stays entirely on one
    # side of zero, even if low, is a real (if weak) ROIC, not a division
    # hazard, and must not raise.
    schedule = roic_fade_schedule(median_roic=0.05, terminal_roic_value=0.08, forecast_years=5)
    assert len(schedule) == 5


def test_roic_fade_schedule_leaves_gulf_oils_own_base_case_unaffected():
    # Day 29's own requirement: GULFOILLUB's real median -> terminal fade
    # (25.89% -> 11.61%, per CRITIQUES.md V8) never approaches zero, so the
    # new floor check must not change its behaviour at all.
    median_roic = historical_median_roic(DEFAULT_FINANCIALS)
    terminal_roic_value = terminal_roic(0.1161)  # same ballpark WACC CRITIQUES.md V8 cites
    assert median_roic == pytest.approx(0.2589, abs=0.01)
    schedule = roic_fade_schedule(median_roic, terminal_roic_value, forecast_years=10, ticker="GULFOILLUB")
    assert len(schedule) == 10
    assert all(rate > 0.05 for rate in schedule)


def test_reinvestment_schedule_from_growth_still_divides_normally_once_the_fade_is_safe():
    schedule = roic_fade_schedule(median_roic=0.20, terminal_roic_value=0.10, forecast_years=4)
    reinvestment = reinvestment_schedule_from_growth(0.05, schedule)
    assert reinvestment == [pytest.approx(0.05 / roic) for roic in schedule]


def test_is_working_capital_release_year_flags_a_fall_in_nwc():
    current = pd.Series({"net_working_capital": 90.0})
    prior = pd.Series({"net_working_capital": 100.0})
    assert is_working_capital_release_year(current, prior)


def test_is_working_capital_release_year_is_false_when_nwc_builds():
    current = pd.Series({"net_working_capital": 110.0})
    prior = pd.Series({"net_working_capital": 100.0})
    assert not is_working_capital_release_year(current, prior)


def test_gulf_oils_latest_fiscal_year_is_a_working_capital_release_year():
    # D6/V1 context: FY2023-24's negative reinvestment rate (-15.68%, see
    # CRITIQUES.md V1) is a working-capital release, not the business
    # disinvesting in its fixed asset base.
    df = to_numeric(load_financials(DEFAULT_FINANCIALS)).set_index("fiscal_year")
    current, prior = df.loc["FY2023-24"], df.loc["FY2022-23"]
    assert is_working_capital_release_year(current, prior)


def test_check_growth_reinvestment_consistency_passes_when_signs_and_roic_agree():
    # growth 10%, reinvestment 40% -> implied ROIC 25%, inside the default band.
    check_growth_reinvestment_consistency(0.10, 0.40)


def test_check_growth_reinvestment_consistency_rejects_positive_growth_with_non_positive_reinvestment():
    with pytest.raises(ValueError):
        check_growth_reinvestment_consistency(0.10, -0.1568)


def test_check_growth_reinvestment_consistency_rejects_an_implausible_implied_roic():
    # growth 10%, reinvestment 1% -> implied ROIC 1000%, outside the default [0%, 100%] band.
    with pytest.raises(ValueError):
        check_growth_reinvestment_consistency(0.10, 0.01)


def test_zero_growth_is_always_consistent_regardless_of_reinvestment_sign():
    # growth=0 has no ROIC claim to make -- any reinvestment rate is fine.
    check_growth_reinvestment_consistency(0.0, -0.1568)


def test_base_case_reinvestment_is_now_consistent_with_positive_forecast_growth():
    # V1 (Day 3-4) pinned reinvestment_rate to FY2023-24's actual, a
    # working-capital release year with a negative rate (-15.68%), pairing
    # it with any positive forecast growth regardless of sign -- the bug
    # this test used to prove by failing (no pytest.raises; it genuinely
    # errored, by design, until this fix landed). V2 (Day 4) replaces that
    # fixed rate with a per-year schedule built from growth / ROIC
    # (:func:`reinvestment_schedule_from_growth`), which satisfies the
    # growth=reinvestment_rate x ROIC identity by construction for every
    # year -- so every year of the schedule now passes the exact same
    # consistency check that used to fail on V1's single flat rate.
    base = base_case_from_financials(DEFAULT_FINANCIALS, revenue_growth=0.10)
    assert isinstance(base.reinvestment_rate, list)
    for rate in base.reinvestment_rate:
        check_growth_reinvestment_consistency(base.revenue_growth, rate)


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
