import math
import statistics
from dataclasses import replace

import pytest

from reverse_dcf.forward import (
    DEFAULT_FINANCIALS,
    TERMINAL_ROIC_SPREAD_DEFAULT,
    base_case_from_financials,
    run_dcf,
)
from reverse_dcf.solve import (
    MARKET_FIXTURES,
    historical_margins_and_reinvestment,
    implied_growth,
    load_market_price,
    solve,
)
from reverse_dcf.sensitivity import plot_tornado, sensitivity_table, to_frame

# V2 (CRITIQUES.md V1): the real market price's own base case is unreachable
# under V2 (see tests/test_solve.py), and shocking WACC/terminal
# growth/EBIT margin by a small amount around an already-unreachable base
# case stays unreachable at one or both ends most of the time (see
# tests/test_sensitivity.py::test_sensitivity_table_reports_the_real_market_price_as_mostly_unreachable
# below for that actual, reportable finding). Tests that check the
# round-trip/ordering *mechanics* instead use a price reachable at both
# shock ends of all five variables, picked by probing. 700 used to work for
# the original four; roic_spread's own -2pp end (CRITIQUES.md V13) pushes
# the ceiling as low as ~681 at this financials fixture, so the price moved
# down to 650 to keep all five fully reachable at both ends.
REACHABLE_PRICE = 650.0


def test_sensitivity_table_covers_all_five_fixed_assumptions():
    # CRITIQUES.md V13: roic_spread joined the other four Day 64.
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    rows = sensitivity_table(market.price, DEFAULT_FINANCIALS)
    assert {r.variable for r in rows} == {
        "wacc",
        "terminal_growth",
        "ebit_margin",
        "reinvestment_rate",
        "roic_spread",
    }


def test_sensitivity_table_is_sorted_by_swing_descending():
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    rows = sensitivity_table(market.price, DEFAULT_FINANCIALS)
    swings = [r.swing for r in rows]
    assert swings == sorted(swings, reverse=True)


def test_sensitivity_rows_are_centered_on_the_actual_base_case():
    # base_value must be the same latest-fiscal-year actual the Day 5 solver
    # itself uses, not an arbitrary sensitivity-only number -- except
    # reinvestment_rate, whose V2 base_value is the historical mean (see
    # sensitivity.py's own note: base.reinvestment_rate at revenue_growth=0.0
    # is V2's all-zero schedule, not a meaningful sensitivity midpoint).
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    base = base_case_from_financials(DEFAULT_FINANCIALS, revenue_growth=0.0)
    _, reinvestment = historical_margins_and_reinvestment(DEFAULT_FINANCIALS)
    reinvestment_mean = statistics.mean(reinvestment.values())
    rows = sensitivity_table(market.price, DEFAULT_FINANCIALS)
    by_variable = {r.variable: r for r in rows}
    assert by_variable["wacc"].base_value == base.wacc
    assert by_variable["terminal_growth"].base_value == base.terminal_growth
    assert by_variable["ebit_margin"].base_value == base.ebit_margin
    assert by_variable["reinvestment_rate"].base_value == pytest.approx(reinvestment_mean)
    assert by_variable["roic_spread"].base_value == TERMINAL_ROIC_SPREAD_DEFAULT
    for r in rows:
        assert r.low_value < r.base_value < r.high_value


def test_sensitivity_table_reports_the_real_market_price_as_mostly_unreachable():
    # The actual Day 4 finding carried through to the tornado: shocking
    # WACC, terminal growth or EBIT margin by a small amount around an
    # already-unreachable base case (see tests/test_solve.py) stays
    # unreachable at the end that would have needed *even more* growth --
    # reported as NaN, not a crash. reinvestment_rate is the one row still
    # fully reachable, because it uses a flat V1-style override (see
    # sensitivity.py's _implied_growth_or_nan / implied_growth's
    # reinvestment_rate escape hatch), which stays monotonic in growth the
    # way V1's whole model always was.
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    rows = sensitivity_table(market.price, DEFAULT_FINANCIALS)
    by_variable = {r.variable: r for r in rows}
    assert not math.isnan(by_variable["reinvestment_rate"].low_growth)
    assert not math.isnan(by_variable["reinvestment_rate"].high_growth)
    for variable in ("wacc", "terminal_growth", "ebit_margin"):
        row = by_variable[variable]
        assert math.isnan(row.low_growth) or math.isnan(row.high_growth)
    # roic_spread (CRITIQUES.md V13): a -2pp spread deepens the shortfall
    # (still unreachable, NaN), but the +2pp end is the one README.md
    # names as reachable -- the dual NaN/finite case plot_tornado's own
    # single-marker branch exists for (see test_roic_spread_pins_the_readme_worked_numbers
    # below for the exact pinned values).
    roic_row = by_variable["roic_spread"]
    assert math.isnan(roic_row.low_growth)
    assert not math.isnan(roic_row.high_growth)


def test_sensitivity_rows_round_trip_through_the_forward_engine():
    # Same "Done when" gate as Day 5: each shocked growth number, fed back
    # through the forward engine at that same shocked assumption, must
    # reproduce the target price - otherwise a bar end is unfalsifiable.
    rows = sensitivity_table(REACHABLE_PRICE, DEFAULT_FINANCIALS)
    for r in rows:
        if r.variable == "terminal_growth":
            base = base_case_from_financials(
                DEFAULT_FINANCIALS, revenue_growth=r.low_growth, terminal_growth=r.low_value
            )
        elif r.variable == "wacc":
            base = base_case_from_financials(DEFAULT_FINANCIALS, revenue_growth=r.low_growth, wacc=r.low_value)
        elif r.variable == "reinvestment_rate":
            # V6 (CRITIQUES.md, Day 18): a flat reinvestment_rate override
            # holds forever, including the terminal year -- reset
            # terminal_reinvestment_rate to None (same reset
            # implied_growth's own override branch applies) so the stale
            # V2-schedule figure baked into `base` doesn't override this
            # flat scenario's own rate.
            base = base_case_from_financials(DEFAULT_FINANCIALS, revenue_growth=r.low_growth)
            base = replace(base, reinvestment_rate=r.low_value, terminal_reinvestment_rate=None)
        elif r.variable == "roic_spread":
            # roic_spread isn't a DcfAssumptions field (unlike wacc/terminal_growth) --
            # it only exists as a base_case_from_financials/implied_growth
            # keyword that reshapes reinvestment_rate and
            # terminal_reinvestment_rate together, so it must be passed in
            # here too rather than bolted on with dataclasses.replace.
            base = base_case_from_financials(
                DEFAULT_FINANCIALS, revenue_growth=r.low_growth, roic_spread=r.low_value
            )
        else:
            base = base_case_from_financials(DEFAULT_FINANCIALS, revenue_growth=r.low_growth)
            base = replace(base, **{r.variable: r.low_value})
        result = run_dcf(base)
        assert result.implied_share_price == pytest.approx(REACHABLE_PRICE, abs=0.01)


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
    rows = sensitivity_table(REACHABLE_PRICE, DEFAULT_FINANCIALS)
    wacc_row = next(r for r in rows if r.variable == "wacc")
    assert wacc_row.high_growth > wacc_row.low_growth


def test_roic_spread_pins_the_readme_worked_numbers():
    # CRITIQUES.md V13: README.md's "Limitations" section hand-probes
    # roic_spread at the real market price and quotes two of its values by
    # hand, with no test pinning them -- unlike every other number this
    # project publishes (its own evidence cell). Pin both so a future change
    # to roic_fade_schedule/terminal_roic can't silently drift them: spread
    # 0% (today's default) stays unreachable with a ~914.55 ceiling; spread
    # 2% (the modest shock sensitivity_table's new roic_spread row now also
    # exercises) flips to reachable at ~+11% implied growth.
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    at_default = solve(market.price, DEFAULT_FINANCIALS, roic_spread=0.0)
    assert at_default.price_reachable is False
    assert at_default.max_achievable_price_10y == pytest.approx(914.55, abs=0.5)

    at_plus_2pp = solve(market.price, DEFAULT_FINANCIALS, roic_spread=0.02)
    assert at_plus_2pp.price_reachable is True
    assert at_plus_2pp.implied_growth == pytest.approx(0.11, abs=0.01)


def test_to_frame_has_one_row_per_variable_and_matches_the_dataclass_rows():
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    rows = sensitivity_table(market.price, DEFAULT_FINANCIALS)
    frame = to_frame(rows)
    assert len(frame) == 5
    assert list(frame["variable"]) == [r.variable for r in rows]
    # NaN != NaN under plain equality (some rows are unreachable at the real
    # market price - see test_sensitivity_table_reports_the_real_market_price_as_mostly_unreachable),
    # so compare with NaN-aware equality rather than a bare list comparison.
    assert frame["swing"].tolist() == pytest.approx([r.swing for r in rows], nan_ok=True)


def test_implied_growth_wacc_override_matches_a_manual_replace():
    # V2 (CRITIQUES.md V1): wacc is a first-class base_case_from_financials
    # parameter precisely so overriding it also moves the ROIC-fade
    # schedule's terminal anchor consistently - a post-hoc
    # dataclasses.replace(base, wacc=...) on a V2 base built at the
    # *unshocked* wacc would carry a reinvestment schedule computed against
    # the wrong wacc, so the manual reconstruction must pass the shocked
    # wacc into base_case_from_financials itself, not bolt it on after.
    base = base_case_from_financials(DEFAULT_FINANCIALS, revenue_growth=0.0)
    shocked_wacc = base.wacc + 0.01

    g = implied_growth(REACHABLE_PRICE, DEFAULT_FINANCIALS, wacc=shocked_wacc)
    shocked_base = base_case_from_financials(DEFAULT_FINANCIALS, revenue_growth=g, wacc=shocked_wacc)
    result = run_dcf(shocked_base)
    assert result.implied_share_price == pytest.approx(REACHABLE_PRICE, abs=0.01)


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
