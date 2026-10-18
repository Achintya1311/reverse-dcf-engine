import pytest

from reverse_dcf.forward import DEFAULT_FINANCIALS
from reverse_dcf.grill import base_year_robustness_check, horizon_sensitivity
from reverse_dcf.solve import MARKET_FIXTURES, load_market_price, solve


def test_base_year_robustness_check_reports_both_cagrs():
    result = base_year_robustness_check(DEFAULT_FINANCIALS)
    assert result["with_fy2014_15"] == pytest.approx(0.1454, abs=0.001)
    # Recomputed from FY2015-16 (dropping the one flagged restructuring
    # year) - a real, independently-checkable number, not restated by
    # construction.
    assert result["without_fy2014_15"] == pytest.approx(0.1586, abs=0.001)


def test_base_year_robustness_check_does_not_weaken_the_finding():
    # The actual Day 9 result: dropping the flagged FY2014-15 base year
    # makes Gulf Oil's realized growth *higher*, not lower - the attack
    # this check exists to run did not break the headline finding. This
    # assertion only holds while that stays true of the committed fixture;
    # if a future fiscal year changes that, the assertion should fail
    # loudly rather than silently pass.
    result = base_year_robustness_check(DEFAULT_FINANCIALS)
    assert result["weakens_finding"] is False


def test_horizon_sensitivity_returns_one_growth_rate_per_horizon():
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    horizons = (5, 10, 15)
    result = horizon_sensitivity(market.price, DEFAULT_FINANCIALS, horizons=horizons)
    assert set(result) == set(horizons)


def test_horizon_sensitivity_10y_matches_day_5_solve():
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    result = horizon_sensitivity(market.price, DEFAULT_FINANCIALS, horizons=(10,))
    base_case = solve(market.price, DEFAULT_FINANCIALS, ticker="GULFOILLUB")
    assert result[10].growth == pytest.approx(base_case.implied_growth)


def test_horizon_sensitivity_stays_well_below_realized_history_at_every_horizon():
    # The Day 9 robustness result this project's REPORT.md relies on:
    # varying the forecast horizon from 5 to 15 years never brings the
    # implied growth anywhere near Gulf Oil's own ~14.5%-15.9% realized
    # growth (see test_base_year_robustness_check_*) - the conclusion's
    # direction is not an artifact of the forecast_years=10 convention.
    #
    # V2 (CRITIQUES.md V1): the real market price is unreachable at the
    # longer horizons under V2 (see test_solve.py), so this property is
    # checked at a price reachable at every horizon in the default set
    # instead -- the structural claim ("never anywhere near 14.5%") is
    # about the model's shape, not about today's specific unreachable price.
    reachable_price = 700.0
    result = horizon_sensitivity(reachable_price, DEFAULT_FINANCIALS)
    assert all(r.reachable for r in result.values())
    assert max(r.growth for r in result.values()) < 0.10


def test_horizon_sensitivity_decreases_with_longer_horizons():
    # Sanity check on direction, not just magnitude. V6 (CRITIQUES.md, Day
    # 18) flipped this test's pre-Day-18 claim ("rises monotonically with
    # horizon"): that direction came from the terminal-value bug letting a
    # longer horizon's terminal year grow forever at no extra reinvestment
    # cost, so a longer horizon looked "more expensive" and needed more
    # growth to compensate. Fixed, a longer explicit horizon gives
    # compounding growth more years to act on price (more leverage per
    # point of growth), so *less* growth is needed to reach the same fixed
    # price -- confirmed to fall monotonically across the default horizon
    # set for this company's own committed financials.
    reachable_price = 700.0
    result = horizon_sensitivity(reachable_price, DEFAULT_FINANCIALS)
    values = [result[y].growth for y in sorted(result)]
    assert values == sorted(values, reverse=True)


def test_horizon_sensitivity_reports_unreachable_horizons_with_their_ceiling():
    # V6 (CRITIQUES.md, Day 18): fixing the terminal-value bug lowers every
    # horizon's price ceiling (the old formula's "free" terminal growth no
    # longer inflates any of them), so the real market price -- already
    # unreachable at the default 10-year horizon (test_solve.py) -- is now
    # unreachable at every horizon in the default set, not just the longer
    # ones V2 alone made unreachable.
    #
    # V9 (CRITIQUES.md, Day 30): "unreachable" alone used to be all a caller
    # got -- the None discarded PriceUnreachableError's own best_growth and
    # best_price_gap. Every unreachable horizon now also reports how close
    # its own best case gets, not just that it fails.
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    result = horizon_sensitivity(market.price, DEFAULT_FINANCIALS)
    assert all(not r.reachable for r in result.values())
    assert all(r.growth is None for r in result.values())
    for r in result.values():
        assert r.ceiling_price is not None
        assert r.ceiling_growth is not None
        # the ceiling is the closest this horizon's bracket gets -- it must
        # actually fall short of the real price, not equal or exceed it
        # (which would mean the horizon was reachable after all).
        assert r.ceiling_price < market.price


def test_horizon_sensitivity_10y_ceiling_matches_day_5_solve():
    # Cross-check against solve()'s own PriceUnreachableError handling
    # (reverse_dcf.solve.solve) rather than re-deriving the ceiling with
    # separate logic that could quietly drift from it.
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    result = horizon_sensitivity(market.price, DEFAULT_FINANCIALS, horizons=(10,))
    base_case = solve(market.price, DEFAULT_FINANCIALS, ticker="GULFOILLUB")
    assert result[10].ceiling_price == pytest.approx(base_case.max_achievable_price_10y)
    assert result[10].ceiling_growth == pytest.approx(base_case.growth_at_max_achievable_price_10y)


def test_cli_runs_end_to_end_against_the_committed_fixtures(monkeypatch, capsys):
    import sys

    from reverse_dcf.grill import main

    monkeypatch.setattr(sys, "argv", ["grill.py"])
    main()
    out = capsys.readouterr().out
    assert "Base-year robustness" in out
    assert "Forecast-horizon robustness" in out
