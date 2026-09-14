from dataclasses import replace

import pandas as pd
import pytest

from reverse_dcf.forward import DEFAULT_FINANCIALS, base_case_from_financials, run_dcf
from reverse_dcf.solve import (
    MARKET_FIXTURES,
    grid_implied_growth,
    historical_margins_and_reinvestment,
    implied_growth,
    load_market_price,
    perpetual_breakeven_growth,
    solve,
)


def test_implied_growth_round_trips_through_the_forward_engine():
    # This is the repo's "Done when" gate: feed the solved growth rate back
    # through the forward DCF and the target price must reproduce within
    # tolerance. Without this the implied number is unfalsifiable.
    target_price = 1061.0
    g = implied_growth(target_price, DEFAULT_FINANCIALS)
    base = base_case_from_financials(DEFAULT_FINANCIALS, revenue_growth=g)
    result = run_dcf(base)
    assert result.implied_share_price == pytest.approx(target_price, abs=0.01)


def test_implied_growth_is_higher_for_a_higher_target_price():
    low = implied_growth(800.0, DEFAULT_FINANCIALS)
    high = implied_growth(2000.0, DEFAULT_FINANCIALS)
    assert high > low


def test_implied_growth_rejects_a_target_price_outside_the_bracket():
    # Wildly higher than what any growth rate in the bracket can produce.
    with pytest.raises(ValueError):
        implied_growth(1e12, DEFAULT_FINANCIALS, bracket=(-0.5, 0.5))


def test_implied_growth_honors_margin_and_reinvestment_overrides():
    base_g = implied_growth(1061.0, DEFAULT_FINANCIALS)
    overridden_g = implied_growth(1061.0, DEFAULT_FINANCIALS, ebit_margin=0.20, reinvestment_rate=0.10)
    assert overridden_g != pytest.approx(base_g)
    # A richer margin and lower reinvestment both raise FCFF per unit of
    # revenue growth, so less growth is needed to reach the same price.
    assert overridden_g < base_g


def test_perpetual_breakeven_growth_round_trips():
    target_price = 1061.0
    g = perpetual_breakeven_growth(target_price, DEFAULT_FINANCIALS)
    base = base_case_from_financials(DEFAULT_FINANCIALS, revenue_growth=g, forecast_years=1, terminal_growth=g)
    result = run_dcf(base)
    assert result.implied_share_price == pytest.approx(target_price, abs=0.01)


def test_perpetual_breakeven_growth_is_below_wacc():
    base = base_case_from_financials(DEFAULT_FINANCIALS, revenue_growth=0.0)
    g = perpetual_breakeven_growth(1061.0, DEFAULT_FINANCIALS)
    assert g < base.wacc


def test_perpetual_breakeven_growth_is_lower_than_the_ten_year_implied_growth():
    # A price that only has to be justified for 10 years before decelerating
    # to the (slower) terminal rate needs a *higher* explicit-period number
    # than the same price would need if that pace literally never ended.
    target_price = 2000.0
    ten_year = implied_growth(target_price, DEFAULT_FINANCIALS)
    forever = perpetual_breakeven_growth(target_price, DEFAULT_FINANCIALS)
    assert forever < ten_year


def test_historical_margins_and_reinvestment_cover_the_ten_fiscal_years():
    margins, reinvestment = historical_margins_and_reinvestment(DEFAULT_FINANCIALS)
    assert len(margins) == 10
    assert len(reinvestment) == 9  # first year has no prior year to diff against
    assert all(0 < m < 1 for m in margins.values())


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
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    result = solve(market.price, DEFAULT_FINANCIALS, ticker="GULFOILLUB")
    assert result.wacc > result.terminal_growth
    assert result.breakeven_growth < result.wacc
    # The result must round-trip too, not just the bare implied_growth() call.
    base = base_case_from_financials(DEFAULT_FINANCIALS, revenue_growth=result.implied_growth)
    assert run_dcf(base).implied_share_price == pytest.approx(market.price, abs=0.01)

    contract = result.to_contract()
    assert contract["valuation"]["implied_cagr"] == pytest.approx(result.implied_growth)
    assert contract["valuation"]["breakeven_growth"] == pytest.approx(result.breakeven_growth)


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
    assert set(written["valuation"]) == {
        "implied_cagr", "implied_ebit_margin", "implied_reinvestment", "breakeven_growth",
    }
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    result = solve(market.price, DEFAULT_FINANCIALS, ticker="GULFOILLUB")
    assert written == result.to_contract()
