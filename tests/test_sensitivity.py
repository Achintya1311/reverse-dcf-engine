from dataclasses import replace

import pytest

from reverse_dcf.forward import DEFAULT_FINANCIALS, base_case_from_financials, run_dcf
from reverse_dcf.solve import MARKET_FIXTURES, implied_growth, load_market_price
from reverse_dcf.sensitivity import plot_tornado, sensitivity_table, to_frame


def test_sensitivity_table_covers_all_four_fixed_assumptions():
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    rows = sensitivity_table(market.price, DEFAULT_FINANCIALS)
    assert {r.variable for r in rows} == {"wacc", "terminal_growth", "ebit_margin", "reinvestment_rate"}


def test_sensitivity_table_is_sorted_by_swing_descending():
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    rows = sensitivity_table(market.price, DEFAULT_FINANCIALS)
    swings = [r.swing for r in rows]
    assert swings == sorted(swings, reverse=True)


def test_sensitivity_rows_are_centered_on_the_actual_base_case():
    # base_value must be the same latest-fiscal-year actual the Day 5 solver
    # itself uses, not an arbitrary sensitivity-only number.
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    base = base_case_from_financials(DEFAULT_FINANCIALS, revenue_growth=0.0)
    rows = sensitivity_table(market.price, DEFAULT_FINANCIALS)
    by_variable = {r.variable: r for r in rows}
    assert by_variable["wacc"].base_value == base.wacc
    assert by_variable["terminal_growth"].base_value == base.terminal_growth
    assert by_variable["ebit_margin"].base_value == base.ebit_margin
    assert by_variable["reinvestment_rate"].base_value == base.reinvestment_rate
    for r in rows:
        assert r.low_value < r.base_value < r.high_value


def test_sensitivity_rows_round_trip_through_the_forward_engine():
    # Same "Done when" gate as Day 5: each shocked growth number, fed back
    # through the forward engine at that same shocked assumption, must
    # reproduce the target price - otherwise a bar end is unfalsifiable.
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    rows = sensitivity_table(market.price, DEFAULT_FINANCIALS)
    for r in rows:
        if r.variable == "terminal_growth":
            base = base_case_from_financials(
                DEFAULT_FINANCIALS, revenue_growth=r.low_growth, terminal_growth=r.low_value
            )
        else:
            base = base_case_from_financials(DEFAULT_FINANCIALS, revenue_growth=r.low_growth)
            base = replace(base, **{r.variable: r.low_value})
        result = run_dcf(base)
        assert result.implied_share_price == pytest.approx(market.price, abs=0.01)


def test_reinvestment_rate_swings_the_implied_growth_the_most():
    # Gulf Oil's own nine years of reinvestment rate swing from roughly -15%
    # to +100% (capex-heavy years) - by far its widest historical range of
    # the four inputs - so it should dominate the tornado.
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    rows = sensitivity_table(market.price, DEFAULT_FINANCIALS)
    assert rows[0].variable == "reinvestment_rate"


def test_higher_wacc_requires_higher_implied_growth():
    # A higher discount rate shrinks the present value of a given growth
    # path, so reproducing the same price needs *more* growth, not less.
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    rows = sensitivity_table(market.price, DEFAULT_FINANCIALS)
    wacc_row = next(r for r in rows if r.variable == "wacc")
    assert wacc_row.high_growth > wacc_row.low_growth


def test_to_frame_has_one_row_per_variable_and_matches_the_dataclass_rows():
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    rows = sensitivity_table(market.price, DEFAULT_FINANCIALS)
    frame = to_frame(rows)
    assert len(frame) == 4
    assert list(frame["variable"]) == [r.variable for r in rows]
    assert list(frame["swing"]) == [r.swing for r in rows]


def test_implied_growth_wacc_override_matches_a_manual_replace():
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    base = base_case_from_financials(DEFAULT_FINANCIALS, revenue_growth=0.0)
    shocked_wacc = base.wacc + 0.01

    g = implied_growth(market.price, DEFAULT_FINANCIALS, wacc=shocked_wacc)
    result = run_dcf(replace(base, wacc=shocked_wacc, revenue_growth=g))
    assert result.implied_share_price == pytest.approx(market.price, abs=0.01)


def test_plot_tornado_writes_a_nonempty_png(tmp_path):
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    rows = sensitivity_table(market.price, DEFAULT_FINANCIALS)
    output = tmp_path / "tornado.png"
    path = plot_tornado(rows, "GULFOILLUB", market.price, output)
    assert path == output
    assert path.exists()
    assert path.stat().st_size > 0


def test_cli_writes_the_tornado_chart_to_the_default_output_path(monkeypatch, capsys, tmp_path):
    import sys

    from reverse_dcf.sensitivity import main

    output = tmp_path / "tornado.png"
    monkeypatch.setattr(sys, "argv", ["sensitivity.py", "--output", str(output)])
    main()
    out = capsys.readouterr().out
    assert "Reinvestment rate" in out
    assert "swing" in out
    assert output.exists()
    assert output.stat().st_size > 0


def test_cli_accepts_an_explicit_price_override(monkeypatch, capsys, tmp_path):
    import sys

    from reverse_dcf.sensitivity import main

    output = tmp_path / "tornado.png"
    monkeypatch.setattr(sys, "argv", ["sensitivity.py", "--price", "1500", "--output", str(output)])
    main()
    out = capsys.readouterr().out
    assert "Rs1,500.00" in out
    assert output.exists()
