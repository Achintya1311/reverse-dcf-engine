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
