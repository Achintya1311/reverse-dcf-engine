import pytest

from reverse_dcf.forward import DEFAULT_FINANCIALS
from reverse_dcf.grill import base_year_robustness_check, horizon_sensitivity, roic_anchor_robustness_check
from reverse_dcf.solve import MARKET_FIXTURES, implied_growth, load_market_price, solve


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


def test_roic_anchor_robustness_check_returns_full_history_and_each_window():
    # V14 (CRITIQUES.md): no robustness check existed for which years anchor
    # historical_median_roic, the third modeling choice grill.py's own
    # mandate names (alongside base year and forecast horizon). This is
    # that third check, mirroring base_year_robustness_check's "compute the
    # headline figure with vs. without a different slice of history" shape.
    windows = (3, 4, 5)
    reachable_price = 700.0
    result = roic_anchor_robustness_check(reachable_price, DEFAULT_FINANCIALS, windows=windows)
    assert set(result["by_window"]) == set(windows)
    assert result["full_history"].reachable is True
    assert all(result["by_window"][w].reachable for w in windows)


def test_roic_anchor_robustness_check_matches_implied_growth_directly():
    # Cross-check against implied_growth's own roic_anchor_years kwarg
    # (test_solve.py) rather than re-deriving the windowed anchor with
    # separate logic that could drift from it.
    reachable_price = 700.0
    result = roic_anchor_robustness_check(reachable_price, DEFAULT_FINANCIALS, windows=(3,))
    direct = implied_growth(reachable_price, DEFAULT_FINANCIALS, roic_anchor_years=3)
    assert result["by_window"][3].growth == pytest.approx(direct)


def test_roic_anchor_robustness_check_moves_away_from_the_full_history_growth():
    # GULFOILLUB's own realized ROIC has a visible declining trend (see
    # test_forward.py), so a trailing window anchored on the most recent
    # fiscal years must give a genuinely different growth rate from the
    # full-history anchor, not the same number by construction.
    reachable_price = 700.0
    result = roic_anchor_robustness_check(reachable_price, DEFAULT_FINANCIALS, windows=(3, 4, 5))
    full = result["full_history"]
    for years in (3, 4, 5):
        assert result["by_window"][years].growth != pytest.approx(full.growth)


def test_roic_anchor_robustness_check_does_not_change_the_real_reachability_conclusion():
    # The actual Day 65 finding: at GULFOILLUB's own committed market
    # price, the headline 10-year conclusion is already "unreachable" under
    # the full-history anchor (test_solve.py). Anchoring on a recent window
    # instead (lower median ROIC, see test_forward.py) makes reinvestment
    # more expensive per unit of growth, which only pushes the ceiling
    # further from the target -- it does not flip "unreachable" to
    # "reachable" for this company's own numbers. Reported honestly either
    # way, not assumed.
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    result = roic_anchor_robustness_check(market.price, DEFAULT_FINANCIALS)
    assert result["full_history"].reachable is False
    assert all(not r.reachable for r in result["by_window"].values())
    assert result["changes_reachability"] is False
    # Each window's ceiling must fall strictly further short of the target
    # than the full-history ceiling, not just differ from it.
    full_gap = market.price - result["full_history"].ceiling_price
    for r in result["by_window"].values():
        assert market.price - r.ceiling_price > full_gap


def test_cli_runs_end_to_end_against_the_committed_fixtures(monkeypatch, capsys):
    import sys

    from reverse_dcf.grill import main

    monkeypatch.setattr(sys, "argv", ["grill.py"])
    main()
    out = capsys.readouterr().out
    assert "Base-year robustness" in out
    assert "Forecast-horizon robustness" in out
    assert "ROIC-anchor" in out


def test_cli_prints_the_valuation_date_check(monkeypatch, capsys):
    import sys

    from reverse_dcf.grill import main

    monkeypatch.setattr(sys, "argv", ["grill.py"])
    main()
    out = capsys.readouterr().out
    assert "4. Valuation-date check" in out
    assert "dated to 2026-10-26" in out
    assert "CHANGES the reachability conclusion" in out.split("4. Valuation-date check")[1]


def test_cli_skips_the_valuation_date_check_for_an_undated_price(monkeypatch, capsys):
    import sys

    from reverse_dcf.grill import main

    monkeypatch.setattr(sys, "argv", ["grill.py", "--price", "1000"])
    main()
    assert "skipped: --price has no date" in capsys.readouterr().out


def test_cli_prints_the_market_weights_check(monkeypatch, capsys):
    import sys

    from reverse_dcf.grill import main

    monkeypatch.setattr(sys, "argv", ["grill.py"])
    main()
    out = capsys.readouterr().out.split("5. Capital-structure check", 1)[1]
    assert "book weights:   WACC 11.76%" in out
    assert "market weights: WACC 11.97%" in out
    assert "does not change the reachability conclusion" in out


def test_market_weights_check_lowers_both_ceilings():
    from reverse_dcf.grill import market_weights_check

    r = market_weights_check(1054.0)
    assert r["market"].wacc > r["book"].wacc
    assert r["market"].ceiling_10y < r["book"].ceiling_10y
    assert r["market"].ceiling_perpetual < r["book"].ceiling_perpetual
    assert r["book"].ceiling_10y == pytest.approx(904.98, abs=0.01)
