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
    assert result[10] == pytest.approx(base_case.implied_growth)


def test_horizon_sensitivity_stays_well_below_realized_history_at_every_horizon():
    # The Day 9 robustness result this project's REPORT.md relies on:
    # varying the forecast horizon from 5 to 15 years never brings the
    # implied growth anywhere near Gulf Oil's own ~14.5%-15.9% realized
    # growth (see test_base_year_robustness_check_*) - the conclusion's
    # direction is not an artifact of the forecast_years=10 convention.
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    result = horizon_sensitivity(market.price, DEFAULT_FINANCIALS)
    assert max(result.values()) < 0.10


def test_horizon_sensitivity_increases_with_longer_horizons():
    # Sanity check on direction, not just magnitude: a longer explicit
    # forecast before the (slower) terminal decay kicks in means less of
    # the low-growth terminal period is priced in, so implied growth should
    # rise monotonically with horizon for this company's assumptions.
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    result = horizon_sensitivity(market.price, DEFAULT_FINANCIALS)
    values = [result[y] for y in sorted(result)]
    assert values == sorted(values)


def test_cli_runs_end_to_end_against_the_committed_fixtures(monkeypatch, capsys):
    import sys

    from reverse_dcf.grill import main

    monkeypatch.setattr(sys, "argv", ["grill.py"])
    main()
    out = capsys.readouterr().out
    assert "Base-year robustness" in out
    assert "Forecast-horizon robustness" in out
