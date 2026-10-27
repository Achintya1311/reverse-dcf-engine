"""D30: REPORT.md is hand-written, so it drifts when the committed fixtures move.

This pins its headline numbers to what ``solve`` prints today. A refresh of
the price or WACC fixtures that changes them fails here until REPORT.md is
brought up to date.
"""

from pathlib import Path

from reverse_dcf.solve import DEFAULT_FINANCIALS, MARKET_FIXTURES, load_market_price, solve
from reverse_dcf.wacc import compute_wacc

REPORT = Path(__file__).resolve().parents[1] / "REPORT.md"


def _result():
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    return market, solve(market.price, DEFAULT_FINANCIALS, ticker="GULFOILLUB")


def test_report_quotes_the_current_ceilings_and_price():
    text = REPORT.read_text()
    market, result = _result()
    contract = result.to_contract()["valuation"]
    assert f"₹{contract['max_achievable_price_10y']:,.2f}/share" in text
    assert f"₹{contract['max_achievable_price_perpetual']:,.2f}/share" in text
    assert f"₹{market.price:,.2f}/share" in text


def test_report_tables_quote_the_current_wacc_and_ceiling_growth():
    # Superseded figures may still appear in the dated history sentences; the tables must be current.
    text = REPORT.read_text()
    wacc = compute_wacc(DEFAULT_FINANCIALS)
    _, result = _result()
    contract = result.to_contract()["valuation"]
    growth = contract["growth_at_max_achievable_price_10y"]
    assert f"| 10-year implied CAGR | **Unreachable** | **₹{contract['max_achievable_price_10y']:,.2f}/share** | +{growth:.2%} |" in text
    assert f"| Perpetual breakeven | **Unreachable** | **₹{contract['max_achievable_price_perpetual']:,.2f}/share** | +{growth:.2%} |" in text
    assert f"| WACC | {wacc.wacc:.2%} |" in text
    assert f"| Terminal growth | {wacc.risk_free_rate:.2%} |" in text


def test_readme_quotes_the_committed_price_and_its_date():
    # D46: the 26 Oct fixture refresh left the README on the 25 Oct price.
    text = (REPORT.parent / "README.md").read_text()
    market, _ = _result()
    lead = next(line for line in text.splitlines() if line.startswith("**Finding"))
    assert f"₹{market.price:,.2f} price of {market.date}" in lead
    assert f"on {market.date} (₹{market.price:,.2f}/share)" in text


def test_report_quotes_the_dated_result_beside_the_undated_one():
    # P99: since V18 the CLI and README report the solve dated to the price
    # date, where the price is reachable; REPORT.md quoted only the undated one.
    text = REPORT.read_text()
    market = load_market_price("GULFOILLUB", MARKET_FIXTURES)
    result = solve(market.price, DEFAULT_FINANCIALS, ticker="GULFOILLUB", price_date=market.date)
    contract = result.to_contract()["valuation"]
    assert contract["price_reachable_dated"]
    row = (
        f"| 10-year implied CAGR, dated to {market.date} (V18) | **{contract['implied_cagr_dated']:.2%}** "
        f"| ₹{contract['max_achievable_price_10y_dated']:,.2f}/share "
        f"| +{contract['growth_at_max_achievable_price_10y_dated']:.2%} |"
    )
    assert row in text
    assert "valued at the FY2023-24 year end" in text
