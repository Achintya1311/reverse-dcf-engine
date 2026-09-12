import pytest

from reverse_dcf.compare import (
    DEFAULT_PEERS,
    comparison_table,
    historical_revenue_cagr,
    load_peer_comparables,
)
from reverse_dcf.forward import DEFAULT_FINANCIALS
from reverse_dcf.solve import MARKET_FIXTURES, load_market_price


def test_historical_revenue_cagr_matches_the_readme_figure():
    # README/checkpoint log have quoted ~14.5% ten-year realized revenue
    # CAGR since Day 2; this is that number, computed rather than retyped.
    cagr = historical_revenue_cagr(DEFAULT_FINANCIALS)
    assert cagr == pytest.approx(0.1454, abs=0.001)


def test_historical_revenue_cagr_rejects_a_single_year(tmp_path):
    one_year = tmp_path / "one_year.csv"
    header = ",".join(
        [
            "fiscal_year",
            "revenue",
            "ebitda",
            "depreciation_amortization",
            "ebit",
            "interest_expense",
            "tax_expense",
            "net_profit",
            "total_assets",
            "total_debt",
            "cash_and_equivalents",
            "net_working_capital",
            "capex",
            "shares_outstanding",
        ]
    )
    one_year.write_text(header + "\nFY2023-24,100,20,5,15,1,3,10,200,50,20,30,5,1000\n")
    with pytest.raises(ValueError):
        historical_revenue_cagr(one_year)


def test_load_peer_comparables_reads_the_committed_fixture():
    peers = load_peer_comparables(DEFAULT_PEERS)
    assert len(peers) >= 3
    assert {"ticker", "name", "statement", "sales_cagr_10y", "source_url"} <= set(peers.columns)
    assert (peers["sales_cagr_10y"].dropna() > -1).all()


def test_load_peer_comparables_includes_gulf_oil_as_a_cross_check_row():
    peers = load_peer_comparables(DEFAULT_PEERS)
    assert "GULFOILLUB" in set(peers["ticker"])


def test_comparison_table_has_one_row_per_implied_and_realized_figure():
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    table = comparison_table(market.price, DEFAULT_FINANCIALS, DEFAULT_PEERS)

    kinds = table["kind"]
    assert kinds.str.contains("implied - 10yr").any()
    assert kinds.str.contains("implied - perpetual breakeven").any()
    assert kinds.str.contains("realized - 10yr history \\(own financials\\)").any()
    # At least the 3 committed peers, each its own row - not the target ticker again.
    peer_rows = table[kinds.str.contains("peer")]
    assert len(peer_rows) >= 3
    assert "GULFOILLUB" not in set(peer_rows["entity"])


def test_comparison_table_implied_growth_matches_day_5_solve():
    from reverse_dcf.solve import solve

    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    table = comparison_table(market.price, DEFAULT_FINANCIALS, DEFAULT_PEERS)
    result = solve(market.price, DEFAULT_FINANCIALS, ticker="GULFOILLUB")

    implied_row = table[table["kind"] == "implied - 10yr (Day 5)"].iloc[0]
    assert implied_row["revenue_cagr"] == pytest.approx(result.implied_growth)


def test_comparison_table_own_realized_history_beats_every_peer():
    # The actual Day 6 finding: Gulf Oil's own ten-year realized revenue
    # CAGR (~14.5%) is higher than any of the three committed lubricant
    # peers' realized ten-year growth - a real result, not assumed true by
    # construction, so this only holds while the committed fixture does.
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    table = comparison_table(market.price, DEFAULT_FINANCIALS, DEFAULT_PEERS)

    own_realized = table.loc[table["kind"] == "realized - 10yr history (own financials)", "revenue_cagr"].iloc[0]
    peer_realized = table[table["kind"].str.contains("peer")]["revenue_cagr"]
    assert own_realized > peer_realized.max()


def test_cli_runs_end_to_end_against_the_committed_fixtures(monkeypatch, capsys):
    import sys

    from reverse_dcf.compare import main

    monkeypatch.setattr(sys, "argv", ["compare.py"])
    main()
    out = capsys.readouterr().out
    assert "implied - 10yr" in out
    assert "Castrol India" in out


def test_cli_accepts_an_explicit_price_override(monkeypatch, capsys):
    import sys

    from reverse_dcf.compare import main

    monkeypatch.setattr(sys, "argv", ["compare.py", "--price", "1500"])
    main()
    out = capsys.readouterr().out
    assert "Rs1,500.00" in out
