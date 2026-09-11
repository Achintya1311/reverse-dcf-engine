# Day 3 — WACC inputs: sourcing and methodology

**Scope for today (per `NEXT_STEPS.md` Day 3):** WACC module - cost of equity from
Damodaran India ERP and beta, cost of debt from the filings, capital structure from
the balance sheet already in `data/GULFOILLUB/financials.csv`.

Network egress to `pages.stern.nyu.edu` (Damodaran Online) and `fred.stlouisfed.org`
(FRED), which Day 2's `sources.md` flagged as blocked as recently as 2026-09-10, is
reachable today (2026-09-11) - confirmed with a live `curl` before writing any code
against it, same as Day 2's unblock. All three fixtures below were pulled live, not
estimated or carried over from memory.

## Industry classification

Gulf Oil Lubricants India Limited (NSEI:GULFOILLUB) is classified **`Chemical
(Basic)`** in Damodaran's own industry mapping, not guessed from its lubricants
business description:

- Source: `indname.xls`, "By company name" sheet
  (<https://pages.stern.nyu.edu/~adamodar/pc/datasets/indname.xls>), row for
  "Gulf Oil Lubricants India Limited (NSEI:GULFOILLUB)" - `Industry Group` =
  `Chemical (Basic)`, `Primary Sector` = `Materials`, `SIC Code` = `2990`,
  `Broad Group` = `Emerging Markets`, `Sub Group` = `India`.
- Fetched 2026-09-11.
- `scripts/fetch_wacc_inputs.py` re-checks this classification every time the
  fixtures are refreshed and refuses to proceed silently if Damodaran has
  reclassified the company.

## Fixture 1 — India country equity risk premium

`fixtures/wacc/india_country_risk_premium.csv`

| Field | Value | Source |
|---|---|---|
| Moody's rating | Baa3 | ctryprem.html, India row |
| Adjusted default spread | 1.87% | ctryprem.html, India row |
| Country risk premium | 2.85% | ctryprem.html, India row |
| **Equity risk premium (used as `ERP_India` in CAPM)** | **7.08%** | ctryprem.html, India row |
| Corporate tax rate (Damodaran's reference figure, not used - see below) | 30.00% | ctryprem.html, India row |

- Source: <https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ctryprem.html>
- The "Equity Risk Premium" column is already the *total* India ERP (mature-market
  ERP plus country risk premium), per the page's own methodology section - used
  directly in `cost_of_equity()`, not added to a separate mature-market figure.
- Fetched 2026-09-11.

## Fixture 2 — India industry beta (Chemical (Basic))

`fixtures/wacc/india_industry_beta.csv`

| Field | Value |
|---|---|
| Number of firms | 152 |
| Beta (levered, industry average) | 0.7703 |
| D/E ratio (industry average) | 0.1099 |
| Effective tax rate (industry average) | 19.99% |
| **Unlevered beta (used as the relevering input)** | **0.7153** |
| Unlevered beta, cash-corrected | 0.7302 |

- Source: <https://pages.stern.nyu.edu/~adamodar/pc/datasets/betaIndia.xls>,
  "Industry Averages" sheet, "Chemical (Basic)" row. Dataset's own "Date updated"
  cell: 2026-01-05.
- **Why the unlevered beta, not the levered one:** the industry-average levered
  beta (0.7703) reflects the *average* Chemical (Basic) company's leverage
  (D/E ≈ 0.11), not Gulf Oil's. Standard Damodaran practice is to unlever the
  industry beta (already done for us in this column) and relever it to the
  target company's own D/E and tax rate - see `reverse_dcf.wacc.relever_beta`.
- **Why not the cash-corrected unlevered beta:** the cash correction removes the
  diluting effect of the *industry's* average cash holdings on its measured
  beta. Since `capital_structure()` already computes Gulf Oil's own leverage from
  its own balance sheet (not the industry's), mixing a cash-corrected industry
  beta with a debt-only relevering step would double-count part of the
  adjustment. Using the plain unlevered beta and relevering only for debt (not
  cash) keeps the two adjustments from overlapping.
- Fetched 2026-09-11.

## Fixture 3 — India risk-free rate

`fixtures/wacc/india_10y_gsec_yield.csv` (trailing 12 monthly observations)

- Source: FRED series `INDIRLTLT01STM`, "Interest Rates: Long-Term Government
  Bond Yields: 10-Year: Main (Including Benchmark) for India"
  (<https://fred.stlouisfed.org/graph/fredgraph.csv?id=INDIRLTLT01STM>).
- `load_risk_free_rate()` uses the most recent observation in the fixture:
  **6.89%** (2026-06-01). FRED/OECD data for this series lags roughly two to
  three months behind the fetch date (2026-09-11), which is normal for this
  series, not a data-quality issue - the trailing 12 months are kept in the
  fixture (rather than only the latest point) precisely so a reader can see
  that lag and the recent trend for themselves.
- Why India's own 10-year government bond yield rather than the US Treasury
  rate: Gulf Oil's financials and this DCF are denominated in INR throughout: a
  USD risk-free rate paired with an INR-denominated cash flow forecast would be
  a currency mismatch inside the discount rate itself.
- Fetched 2026-09-11.

## Company-specific inputs (not fetched - derived from `data/GULFOILLUB/financials.csv`)

These do not need a citation ledger entry of their own: every underlying cell they
derive from is already cited in `research/sources.md` from Day 2. Documented here
is only the *formula*, not a new source.

- **Effective tax rate** (used both for the after-tax cost of debt and to relever
  beta): `tax_expense / (ebit - interest_expense)` for FY2023-24 =
  `10535.66 / (43906.45 - 2560.94)` = **25.48%**. `ebit - interest_expense`
  recovers pre-tax income without a separate PBT column, since `financials.py`
  already defines `ebit = PBT + finance costs`.
- **Cost of debt (pre-tax)**: `interest_expense / average(total_debt over
  FY2022-23 and FY2023-24)` = `2560.94 / 33044.665` = **7.75%**. Averaged
  rather than year-end, to smooth a mid-year borrowing or repayment rather than
  measuring against whichever balance happened to be on the books at the
  fiscal-year-end snapshot.
- **Capital structure**: `total_debt` = ₹32,931.01 lakh (FY2023-24) against a
  book-equity proxy of `total_assets - total_debt` = ₹197,518.90 lakh, giving
  weights of 14.29% debt / 85.71% equity. See `capital_structure()`'s
  docstring and the README limitations section for exactly what this proxy
  assumes away.

## Result (FY2023-24, `python -m reverse_dcf.wacc`)

```
WACC assumptions -- FY2023-24 (Gulf Oil Lubricants India)
  Risk-free rate (India 10Y G-Sec, latest FRED obs.): 6.89%
  India equity risk premium (Damodaran):              7.08%
  Industry unlevered beta (Chemical (Basic), India): 0.7153
  Relevered to Gulf Oil's own D/E and tax rate:       0.8041
  Cost of equity (CAPM):                              12.58%
  Effective tax rate (FY2023-24):              25.48%
  Cost of debt, pre-tax:                               7.75%
  Cost of debt, after-tax:                             5.78%
  Weight of debt / equity (book):                     14.29% / 85.71%
  WACC:                                                11.61%
```

Not a precision claim - see the README limitations section for the book-vs-market
capital structure caveat and what a bottom-up beta assumes.
