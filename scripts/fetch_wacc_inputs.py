"""Rebuild fixtures/wacc/*.csv from live sources (Day 3).

Not part of the WACC module's runtime path - `reverse_dcf.wacc` only reads
the committed CSV fixtures, so tests and `python -m reverse_dcf.wacc` never
need network access. This script exists so the fixtures are reproducible
rather than a one-off hand-transcription: re-run it to refresh the India
ERP, industry beta and risk-free-rate inputs when Damodaran's annual
update or a new FRED observation lands.

Needs `requests` and `xlrd` (for Damodaran's legacy .xls files) - neither
is in requirements.txt because nothing at runtime imports them. Install
both ad hoc (`pip install requests xlrd`) before running this script.

Usage:
    python scripts/fetch_wacc_inputs.py
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "fixtures" / "wacc"

CTRYPREM_URL = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ctryprem.html"
BETA_INDIA_URL = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/betaIndia.xls"
INDNAME_URL = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/indname.xls"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=INDIRLTLT01STM"

INDUSTRY = "Chemical (Basic)"  # Gulf Oil Lubricants India's Damodaran classification - see research/wacc_sources.md


def fetch_india_erp(fetched_date: str) -> pd.DataFrame:
    # The page is an Excel-exported HTML table with no stable column
    # attributes to key off - pd.read_html would need lxml/html5lib just to
    # get the same eight `<td>` cells a plain regex over the India row
    # already gives cleanly (verified by hand against the live page).
    html = requests.get(CTRYPREM_URL, timeout=30).text
    idx = html.find(">India<")
    if idx == -1:
        raise SystemExit("'India' row not found in ctryprem.html - page layout may have changed")
    cells = re.findall(r"<td[^>]*>([^<]*)</td>", html[idx : idx + 1500])[:7]
    moodys, default_spread, country_premium, erp, tax_rate, cds, erp_cds = cells
    return pd.DataFrame(
        [
            {
                "country": "India",
                "moodys_rating": moodys,
                "adj_default_spread_pct": float(default_spread.rstrip("%")),
                "country_risk_premium_pct": float(country_premium.rstrip("%")),
                "equity_risk_premium_pct": float(erp.rstrip("%")),
                "corporate_tax_rate_pct": float(tax_rate.rstrip("%")),
                "sovereign_cds_pct": float(cds.rstrip("%")),
                "erp_based_on_cds_pct": float(erp_cds.rstrip("%")),
                "source_url": CTRYPREM_URL,
                "fetched_date": fetched_date,
            }
        ]
    )


def fetch_industry_beta(fetched_date: str) -> pd.DataFrame:
    raw = requests.get(BETA_INDIA_URL, timeout=30).content
    updated = pd.read_excel(io.BytesIO(raw), sheet_name="Industry Averages", header=None).iloc[0, 1]
    df = pd.read_excel(io.BytesIO(raw), sheet_name="Industry Averages", header=9).dropna(subset=["Industry Name"])
    row = df[df["Industry Name"].astype(str).str.strip() == INDUSTRY].iloc[0]
    return pd.DataFrame(
        [
            {
                "industry_name": INDUSTRY,
                "num_firms": int(row["Number of firms"]),
                "beta": row["Beta "],
                "de_ratio": row["D/E Ratio"],
                "effective_tax_rate_pct": row["Effective Tax rate"] * 100,
                "unlevered_beta": row["Unlevered beta"],
                "unlevered_beta_cash_corrected": row["Unlevered beta corrected for cash"],
                "source_url": BETA_INDIA_URL,
                "source_sheet": "Industry Averages",
                "data_updated": pd.Timestamp(updated).date().isoformat(),
                "fetched_date": fetched_date,
            }
        ]
    )


def fetch_risk_free_rate(fetched_date: str, trailing_months: int = 12) -> pd.DataFrame:
    text = requests.get(FRED_URL, timeout=30).text
    df = pd.read_csv(io.StringIO(text), names=["date", "yield_pct"], header=0)
    return df.tail(trailing_months).reset_index(drop=True)


def verify_industry_classification() -> str:
    """Confirm Gulf Oil Lubricants India's Damodaran industry group from indname.xls.

    Returns the industry name found, to catch silently at the source if
    Damodaran ever reclassifies the company - this script shouldn't keep
    fetching ``Chemical (Basic)`` beta data for a company that has moved
    to a different industry group without saying so.
    """
    raw = requests.get(INDNAME_URL, timeout=60).content
    df = pd.read_excel(io.BytesIO(raw), sheet_name="By company name", header=0)
    match = df[df["Company Name"].astype(str).str.contains("Gulf Oil Lubricants India", case=False, na=False)]
    if match.empty:
        raise SystemExit("Gulf Oil Lubricants India not found in indname.xls 'By company name' sheet")
    return str(match.iloc[0]["Industry Group"])


def main() -> None:
    fetched_date = pd.Timestamp.now().date().isoformat()

    classification = verify_industry_classification()
    if classification != INDUSTRY:
        sys.exit(
            f"indname.xls now classifies Gulf Oil Lubricants India as {classification!r}, "
            f"not {INDUSTRY!r} - update INDUSTRY and research/wacc_sources.md before refreshing fixtures."
        )

    fetch_india_erp(fetched_date).to_csv(OUT / "india_country_risk_premium.csv", index=False)
    fetch_industry_beta(fetched_date).to_csv(OUT / "india_industry_beta.csv", index=False)
    fetch_risk_free_rate(fetched_date).to_csv(OUT / "india_10y_gsec_yield.csv", index=False)
    print(f"fixtures/wacc/*.csv refreshed from live sources ({fetched_date})")


if __name__ == "__main__":
    main()
