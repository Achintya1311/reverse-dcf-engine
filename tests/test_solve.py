from dataclasses import replace

import pandas as pd
import pytest

from reverse_dcf.forward import DEFAULT_FINANCIALS, base_case_from_financials, run_dcf
from reverse_dcf.solve import (
    MARKET_FIXTURES,
    PriceUnreachableError,
    grid_implied_growth,
    historical_margins_and_reinvestment,
    historical_roic_by_year,
    implied_growth,
    load_market_price,
    perpetual_breakeven_growth,
    solve,
    working_capital_release_years,
)

# V2 (CRITIQUES.md V1/V2): tying reinvestment to growth via ROIC means price
# is no longer monotonically increasing in growth -- see
# reverse_dcf.forward.roic_fade_schedule's docstring. At GULFOILLUB's own
# committed market price (Rs1,061.00, fixtures/market/GULFOILLUB.csv), that
# is not hypothetical: it is genuinely unreachable under both the 10-year
# model (ceiling ~Rs962) and the perpetual one (ceiling ~Rs715) -- see
# test_solve_at_the_real_market_price_is_honestly_unreachable_under_v2 below,
# which is the actual, reportable finding. Tests that exist to check the
# round-trip/ordering *mechanics* instead use prices comfortably inside both
# ceilings, picked by probing (not tuned to flatter any one assertion).
REACHABLE_BY_BOTH_MODELS = 700.0
REACHABLE_BY_10Y_ONLY = 900.0


def test_implied_growth_round_trips_through_the_forward_engine():
    # This is the repo's "Done when" gate: feed the solved growth rate back
    # through the forward DCF and the target price must reproduce within
    # tolerance. Without this the implied number is unfalsifiable.
    target_price = REACHABLE_BY_10Y_ONLY
    g = implied_growth(target_price, DEFAULT_FINANCIALS)
    base = base_case_from_financials(DEFAULT_FINANCIALS, revenue_growth=g)
    result = run_dcf(base)
    assert result.implied_share_price == pytest.approx(target_price, abs=0.01)


def test_implied_growth_is_higher_for_a_higher_target_price():
    low = implied_growth(REACHABLE_BY_BOTH_MODELS, DEFAULT_FINANCIALS)
    high = implied_growth(REACHABLE_BY_10Y_ONLY, DEFAULT_FINANCIALS)
    assert high > low


def test_implied_growth_rejects_a_target_price_outside_the_bracket():
    # Wildly higher than what any growth rate in the bracket can produce.
    with pytest.raises(ValueError):
        implied_growth(1e12, DEFAULT_FINANCIALS, bracket=(-0.5, 0.5))


def test_solve_at_the_real_market_price_is_honestly_unreachable_under_v2():
    # The actual Day 4 finding, not a hypothetical: at GULFOILLUB's own
    # committed market price, V2's growth/ROIC-consistent reinvestment
    # schedule cannot produce that price at *any* constant explicit growth
    # rate. Both solves raise PriceUnreachableError, and each error carries
    # the bracket's own best case so a caller (solve(), compare.py, grill.py)
    # can report how unreachable the target is instead of crashing.
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    with pytest.raises(PriceUnreachableError) as excinfo:
        implied_growth(market.price, DEFAULT_FINANCIALS)
    assert excinfo.value.best_price_gap < 0  # the best case still falls short of the target
    assert market.price + excinfo.value.best_price_gap < market.price

    with pytest.raises(PriceUnreachableError):
        perpetual_breakeven_growth(market.price, DEFAULT_FINANCIALS)


def test_implied_growth_honors_margin_and_reinvestment_overrides():
    target_price = REACHABLE_BY_10Y_ONLY
    base_g = implied_growth(target_price, DEFAULT_FINANCIALS)
    overridden_g = implied_growth(target_price, DEFAULT_FINANCIALS, ebit_margin=0.20, reinvestment_rate=0.10)
    assert overridden_g != pytest.approx(base_g)
    # A richer margin and a flat, V1-style reinvestment override both raise
    # FCFF per unit of revenue growth relative to V2's growth-scaled
    # schedule, so less growth is needed to reach the same price.
    assert overridden_g < base_g


def test_perpetual_breakeven_growth_round_trips():
    target_price = REACHABLE_BY_BOTH_MODELS
    g = perpetual_breakeven_growth(target_price, DEFAULT_FINANCIALS)
    base = base_case_from_financials(DEFAULT_FINANCIALS, revenue_growth=g, forecast_years=1, terminal_growth=g)
    result = run_dcf(base)
    assert result.implied_share_price == pytest.approx(target_price, abs=0.01)


def test_perpetual_breakeven_growth_is_below_wacc():
    base = base_case_from_financials(DEFAULT_FINANCIALS, revenue_growth=0.0)
    g = perpetual_breakeven_growth(REACHABLE_BY_BOTH_MODELS, DEFAULT_FINANCIALS)
    assert g < base.wacc


def test_perpetual_breakeven_growth_is_now_higher_than_the_ten_year_implied_growth():
    # V1's claim here was the opposite of this test's new name: a price that
    # only has to be justified for 10 years before decelerating needs a
    # *higher* explicit growth number than the same price held forever,
    # because V1's reinvestment rate was fixed regardless of growth, so
    # price rose without limit as growth rose - a longer high-growth window
    # before the (slower) terminal rate was always the "easier" way to a
    # given price.
    #
    # V2 breaks that: reinvestment scales with growth
    # (reinvestment_schedule_from_growth), so 10 years of explicit growth
    # now *costs* 10 years of growth-scaled reinvestment, while the
    # perpetual model's single terminal-ROIC reinvestment rate is the only
    # cost the one-year collapse ever pays. The 10-year model's own
    # zero-growth price (~Rs960, base_case_from_financials at g=0) already
    # exceeds the perpetual model's entire reachable range (ceiling ~Rs715,
    # g -> wacc) -- so for any price both models can reach, the 10-year
    # model gets there with *negative* growth (pulling price down from
    # ~960) while the perpetual model needs zero-or-positive growth
    # (pushing price up from its own, much lower, zero-growth price
    # ~Rs649) to reach the same number. forever > ten_year now, not <.
    target_price = REACHABLE_BY_BOTH_MODELS
    ten_year = implied_growth(target_price, DEFAULT_FINANCIALS)
    forever = perpetual_breakeven_growth(target_price, DEFAULT_FINANCIALS)
    assert ten_year < 0
    assert forever > ten_year


def test_historical_margins_and_reinvestment_cover_the_ten_fiscal_years():
    margins, reinvestment = historical_margins_and_reinvestment(DEFAULT_FINANCIALS)
    assert len(margins) == 10
    assert len(reinvestment) == 9  # first year has no prior year to diff against
    assert all(0 < m < 1 for m in margins.values())


def test_historical_roic_by_year_covers_nine_fiscal_years():
    roic = historical_roic_by_year(DEFAULT_FINANCIALS)
    assert len(roic) == 9  # first year has no prior year to use as invested capital
    assert "FY2023-24" in roic


def test_historical_roic_by_year_matches_hand_computed_latest_fiscal_year():
    # NOPAT(FY24) = ebit(43906.45) * (1 - tax_rate); tax_rate = tax_expense /
    # (ebit - interest_expense) = 10535.66 / (43906.45 - 2560.94).
    # invested_capital(FY23) = total_assets(207157.15) - cash(65036.0).
    roic = historical_roic_by_year(DEFAULT_FINANCIALS)
    tax_rate = 10535.66 / (43906.45 - 2560.94)
    nopat = 43906.45 * (1 - tax_rate)
    expected = nopat / (207157.15 - 65036.0)
    assert roic["FY2023-24"] == pytest.approx(expected)


def test_working_capital_release_years_includes_the_latest_fiscal_year():
    # V1: FY2023-24's net working capital fell from 50111.89 to 47469.15.
    release_years = working_capital_release_years(DEFAULT_FINANCIALS)
    assert "FY2023-24" in release_years
    assert len(release_years) < 9  # not every year is a release year


def test_grid_implied_growth_shape_and_round_trip_on_one_cell():
    margins = [0.15, 0.18]
    reinvestment_rates = [-0.05, 0.10]
    grid = grid_implied_growth(1061.0, DEFAULT_FINANCIALS, margins=margins, reinvestment_rates=reinvestment_rates)
    assert list(grid.index) == margins
    assert list(grid.columns) == reinvestment_rates

    g = grid.loc[0.15, 0.10]
    base = base_case_from_financials(DEFAULT_FINANCIALS, revenue_growth=g)
    base = replace(base, ebit_margin=0.15, reinvestment_rate=0.10)
    result = run_dcf(base)
    assert result.implied_share_price == pytest.approx(1061.0, abs=0.01)


def test_grid_implied_growth_leaves_nan_where_no_root_exists_in_bracket():
    # Reinvestment rate > 1 flips FCFF negative every year; a target price
    # far above what that combination can ever produce has no root.
    grid = grid_implied_growth(
        1e6, DEFAULT_FINANCIALS, margins=[0.15], reinvestment_rates=[1.5], bracket=(-0.5, 0.5)
    )
    assert pd.isna(grid.loc[0.15, 1.5])


def test_load_market_price_reads_the_committed_fixture():
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    assert market.price > 0
    assert market.market_cap_cr > 0
    assert market.source_url.startswith("https://")


def test_solve_returns_a_consistent_result_and_contract_block():
    # A price reachable by both models, so the ordinary consistent-result
    # path (round trip, contract shape) is what's exercised here; the real
    # market price's genuine V2 unreachability has its own test below.
    target_price = REACHABLE_BY_BOTH_MODELS
    result = solve(target_price, DEFAULT_FINANCIALS, ticker="GULFOILLUB")
    assert result.price_reachable
    assert result.breakeven_reachable
    assert result.wacc > result.terminal_growth
    assert result.breakeven_growth < result.wacc
    # The result must round-trip too, not just the bare implied_growth() call.
    base = base_case_from_financials(DEFAULT_FINANCIALS, revenue_growth=result.implied_growth)
    assert run_dcf(base).implied_share_price == pytest.approx(target_price, abs=0.01)

    contract = result.to_contract()
    assert contract["valuation"]["implied_cagr"] == pytest.approx(result.implied_growth)
    assert contract["valuation"]["breakeven_growth"] == pytest.approx(result.breakeven_growth)


def test_solve_at_the_real_market_price_reports_unreachable_gracefully():
    # solve() must never crash on the CLI's own default price -- it reports
    # the honest "no growth rate under V2 reproduces this" outcome instead.
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    result = solve(market.price, DEFAULT_FINANCIALS, ticker="GULFOILLUB")
    assert result.price_reachable is False
    assert result.implied_growth is None
    assert result.max_achievable_price_10y < market.price
    assert result.breakeven_reachable is False
    assert result.breakeven_growth is None
    assert result.max_achievable_price_perpetual < market.price

    contract = result.to_contract()
    assert contract["valuation"]["implied_cagr"] is None
    assert contract["valuation"]["price_reachable"] is False


def test_cli_runs_end_to_end_against_the_committed_fixture(monkeypatch, capsys):
    import sys

    from reverse_dcf.solve import main

    monkeypatch.setattr(sys, "argv", ["solve.py"])
    main()
    out = capsys.readouterr().out
    assert "Implied revenue growth" in out
    assert "Perpetual breakeven growth" in out


def test_cli_grid_flag_prints_the_sensitivity_table(monkeypatch, capsys):
    import sys

    from reverse_dcf.solve import main

    monkeypatch.setattr(sys, "argv", ["solve.py", "--grid"])
    main()
    out = capsys.readouterr().out
    assert "ebit_margin" in out
    assert "reinvestment_rate" in out


def test_cli_accepts_an_explicit_price_override(monkeypatch, capsys):
    import sys

    from reverse_dcf.solve import main

    monkeypatch.setattr(sys, "argv", ["solve.py", "--price", "1500"])
    main()
    out = capsys.readouterr().out
    assert "Rs1,500.00" in out


def test_cli_contract_flag_writes_the_v0_7_json_block(monkeypatch, capsys, tmp_path):
    import json
    import sys

    from reverse_dcf.solve import main

    contract_path = tmp_path / "valuation.json"
    monkeypatch.setattr(sys, "argv", ["solve.py", "--contract", str(contract_path)])
    main()

    out = capsys.readouterr().out
    assert f"wrote valuation contract to {contract_path}" in out

    written = json.loads(contract_path.read_text())
    required_keys = {"implied_cagr", "implied_ebit_margin", "implied_reinvestment", "breakeven_growth"}
    assert required_keys <= set(written["valuation"])
    # The CLI's default price is the real committed market-price fixture,
    # which V2 cannot reach at any growth rate (see
    # test_solve_at_the_real_market_price_reports_unreachable_gracefully) --
    # the contract says so honestly instead of carrying a fabricated number.
    assert written["valuation"]["implied_cagr"] is None
    assert written["valuation"]["price_reachable"] is False

    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    result = solve(market.price, DEFAULT_FINANCIALS, ticker="GULFOILLUB")
    assert written == result.to_contract()
