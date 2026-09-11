# Day 2 — sourcing status: DONE (2026-09-11)

**Scope for today (per `NEXT_STEPS.md` Day 2):** hand-enter ten years of Gulf Oil
Lubricants India (NSE: GULFOILLUB) financials into `data/GULFOILLUB/financials.csv`,
every figure cited to a document and page in this file.

Completed 2026-09-11 after the sandbox's egress allowlist was widened to reach
`india.gulfoilltd.com` (see the dated entries below for the blocked history and
the unblock). All ten fiscal years (FY2014-15 through FY2023-24) are transcribed
from primary-source annual reports, with a methodology section and full citation
ledger below.

## What happened

This sandbox's network egress proxy rejects every direct connection to an external
host with `403` ("policy denial"), confirmed against all of the following on
2026-09-10:

- `india.gulfoilltd.com` (Gulf Oil's own investor-relations annual report archive —
  the exact source Day 1 picked this company for) — `curl` and `WebFetch` both
  rejected with `EGRESS_BLOCKED` / connect_rejected.
- `www.screener.in`, `www.moneycontrol.com`, `www.nseindia.com`, `www.bseindia.com`
  — same rejection. No financial-data aggregator is reachable either.
- `pages.stern.nyu.edu` (Damodaran Online, needed for Day 3's WACC inputs) and
  `fred.stlouisfed.org` (risk-free rate, also Day 3) — same rejection. Worth
  flagging now since Day 3 will hit the identical wall.

Only the `WebSearch` tool returns anything, and it returns third-party search
snippets and summaries, not the source PDF. It cannot deliver a page number inside
an annual report — there is no PDF to open. A sample snippet from today (via
`WebSearch`, not a primary source): equitymaster.com's write-up of the FY2023-24
annual report states operating income rose 10.1% YoY and net profit rose 32.6% YoY
with margin expanding 7.7%→9.3%, and that FY24 dividends totaled ₹36/share. That is
real information, attributed to equitymaster's analysis of the report, but it is
three summary figures for one year out of ten, sourced to a third party's
commentary rather than the filing itself — not what "every figure cited to a
document and page" requires, and not remotely the ten years of full
income-statement/balance-sheet/cash-flow detail the DCF engine needs as line items.

## Why this isn't worked around with a fixture

Every other project in this portfolio ships `fixtures/` so a failing live fetch
falls back to committed sample data for code and tests to run against. That pattern
doesn't apply here: Day 2's output isn't code exercising a data source, it *is* the
primary-source data. There is no honest fixture for "what page 47 of the FY2018-19
annual report says" — inventing plausible-looking numbers and page numbers would be
fabricating the input to a valuation model and cannot be reconciled with this
portfolio's own honesty rule. Recording the block is the correct outcome, not a
last resort.

## Resume point

Once network egress reaches `india.gulfoilltd.com` (or an equivalent primary-source
archive), Day 2 resumes exactly as scoped:

1. Pull the FY2014-15 through FY2023-24 annual report PDFs from
   `india.gulfoilltd.com/investors/annual-reports`.
2. For each year, transcribe revenue, EBITDA, D&A, EBIT, interest, tax, net profit,
   total assets, total debt, cash, net working capital, capex and shares
   outstanding from the standalone (or consolidated, whichever the model settles
   on — decide and record that choice here) financial statements.
3. Cite every cell to `<report file/year>, p.<n>` in this file, one row per figure,
   before `data/GULFOILLUB/financials.csv` is considered final.

If Gulf Oil's own archive stays unreachable but a mirror of the same filings
becomes reachable (NSE/BSE corporate-filings pages, for instance), that's an
acceptable substitute source — cite it the same way, filing and page.

## 2026-09-10 (second run) — same block, sharper diagnosis

Re-tested before redoing Day 2 in case the block was transient. It is not:
identical `403` rejections on the exact same five hosts as the first run,
plus a categorical check this time against unrelated, non-finance hosts —
`www.google.com`, `en.wikipedia.org` and `web.archive.org` were rejected the
same way. Only a short allowlist of package-registry-style hosts (`pypi.org`,
`files.pythonhosted.org`, `api.github.com`, `raw.githubusercontent.com`, etc.)
is reachable. That rules out "this specific site is down" or "finance sites
are singled out" — it's a sandbox-wide egress allowlist that has nothing on
it for fetching documents. Retrying the same hosts again tomorrow without a
policy change will produce the same result, so the correct move today is not
to keep re-testing but to make the parts of Day 2 that don't need a live
fetch as ready as possible, and record the resume path precisely.

**What resuming actually needs — either one:**

1. The sandbox's network egress allowlist grows an entry for
   `india.gulfoilltd.com` (or another primary-source filing archive). Then
   Day 2 resumes exactly as scoped above.
2. A human places the source PDFs (or extracted text/page images) for the
   FY2014-15 through FY2023-24 Gulf Oil Lubricants India annual reports under
   `sources/raw/GULFOILLUB/` in this repo. A future run can then transcribe
   figures from those local files with page citations — no live fetch needed
   for that path at all.

**What did move today:** the Day 2 *schema* is now committed and tested even
though the Day 2 *data* still is not. `data/GULFOILLUB/financials.csv` has
the ten fiscal-year rows and the line-item columns the reverse DCF needs
(`reverse_dcf/financials.py` defines and validates them), every cell holding
the literal string `PENDING` rather than a number — there is no honest way to
fill those cells without the source documents, so they stay placeholders.
`tests/test_financials_schema.py` locks the column set and fiscal-year
coverage now and will start failing, cell by cell, as real figures replace
`PENDING` — a mechanical prompt for a future run to update it as sourcing
actually completes. The citation ledger below is empty for the same reason:
there is nothing to cite yet.

## 2026-09-11 (third run) — same block, one open decision resolved

Checked `sources/raw/GULFOILLUB/` for human-dropped annual-report PDFs (the
resume path 2 above) — the directory doesn't exist, nothing was dropped.
Re-tested network egress: the proxy's own status endpoint
(`$HTTPS_PROXY/__agentproxy/status`) logs today's attempt to
`india.gulfoilltd.com:443` and `www.screener.in:443` as `connect_rejected`,
`"gateway answered 403 to CONNECT (policy denial or upstream failure)"` — the
proxy's own operator docs (`/root/.ccr/README.md`) say a 403 from the gateway
is an organization egress policy denial and explicitly say not to keep
retrying it, which matches the categorical, non-flaky pattern established on
2026-09-09 and 2026-09-10. Recorded here rather than re-run again tomorrow:
future days should check `sources/raw/GULFOILLUB/` for dropped source files
first and, finding nothing, go straight to recording blocked instead of
re-diagnosing the identical proxy policy a fourth time.

Used the time instead to close the one open modeling decision Day 2's schema
was still silent on: **standalone vs. consolidated financials.** Resolved
as: prefer Gulf Oil Lubricants India's **consolidated** financial statements
for all ten fiscal years, if the annual reports publish them. The reverse
DCF is being run against the *listed* entity's market capitalization, which
prices the economic interest attributable to its shareholders across
whatever it consolidates (including any subsidiaries/JVs), not just the
parent entity's own standalone books — using standalone financials when a
consolidated statement exists would misstate free cash flow by the
subsidiaries' contribution. Fall back to standalone, noted explicitly per
affected fiscal year in the citation ledger, only for years where the
annual report does not present a consolidated statement (common for older
filings before consolidation became mandatory, or for a company with no
reportable subsidiaries in that year). This is a policy for the transcriber
to apply once sourcing unblocks, not a claim about Gulf Oil's actual
corporate structure — that gets settled per filing, cited like any other
figure, when the documents can finally be read.

## 2026-09-11 (unblocked) — sourcing complete, standalone/consolidated decision revised

The sandbox's egress allowlist was widened to reach `india.gulfoilltd.com`
(confirmed via the proxy status endpoint and a live `curl`). Re-verified the
resume path was still needed before doing anything else — `screener.in`,
`bseindia.com`, NYU Stern (Damodaran) and FRED all came back reachable too,
so Day 3's WACC inputs should be unblocked when that day comes.

Downloaded all ten annual reports from `india.gulfoilltd.com/investors/annual-reports`,
with one exception: **FY2018-19** is not listed there at all (only its Business
Responsibility Report, MGT-9 extract and proxy form are — the bound annual
report itself is missing from Gulf Oil's own archive). Sourced that one year
from BSE India's corporate-filings mirror instead (scrip code 538567,
`bseindia.com/bseplus/AnnualReport/538567/5385670319.pdf`), matched against
screener.in's year index to confirm it's the FY2018-19 filing (its cover page
confirms "ANNUAL REPORT 2018-19"), per the resume plan's "an acceptable
substitute source" clause above. The **FY2022-23** annual report is likewise
filed under an unexpected name on Gulf Oil's own site
(`Gulf_Oil_AR_2023_C2C_Design_v8_09.08.2023-1.pdf`, alongside the AGM notice
and BRSR for that year) — confirmed by its own cover page before use.

**Revised the standalone-vs-consolidated decision made earlier today.** The
plan above was to prefer consolidated statements wherever the annual report
publishes them. Having now read the actual filings: Gulf Oil Lubricants India
has **no subsidiary for nine of the ten fiscal years** in this window. Its
Consolidated Financial Statements first appear as a substantive statement
(not boilerplate "the Company has no subsidiary" policy text) in FY2023-24,
and even there the cash flow statement shows "Payment for acquisition of
subsidiary ₹10,250.88 Lakhs" as an FY2023-24 investing-activity line — the
subsidiary was acquired *during* that year, so a consolidated FY2023-24
would carry only a partial year of its contribution. Using consolidated
figures for one year out of ten, with a mid-year acquisition discontinuity
baked in, would introduce a break in the growth series that has nothing to
do with the core lubricants business's organic performance — exactly the
kind of artifact an implied-CAGR analysis (Day 5) needs to not be fooled by.
**Decision: standalone financials for all ten years**, for comparability
across the full window. This is a comparability call, not a claim that
consolidated numbers are wrong; if a later day (the Day 6 comparison, or the
three-statement model in project 8) needs the FY2023-24 subsidiary's
contribution called out separately, it can be added as an annotation without
touching the other nine years.

## Methodology — how the derived columns are computed

Every fiscal year's `data/GULFOILLUB/financials.csv` row combines figures
reported as-is with a small number of derived columns computed by a fixed
rule, documented once here (and mirrored in the `reverse_dcf/financials.py`
module docstring) rather than repeated per cell:

- `revenue` — Revenue from operations, **net** of excise duty. Gulf Oil's
  pre-GST-era statements (FY2016-17 and FY2017-18, the only two years Ind AS
  required revenue gross of excise duty with excise shown as a matching
  expense line) had excise duty netted back out here for comparability with
  the post-GST years, where revenue is already reported net of indirect
  taxes. This reclassification doesn't touch profit before tax: the same
  amount is removed from both revenue and expenses.
- `interest_expense` — Finance costs, as reported in the Statement of Profit
  and Loss (single line).
- `depreciation_amortization` — Depreciation and amortisation expense, as
  reported (single line).
- `ebit` = Profit before tax + Finance costs (interest added back). For the
  two years (FY2014-15, FY2015-16) whose P&L explicitly reports "Profit
  before Finance Costs, Depreciation and Amortization Expense and Tax
  Expense" (i.e. EBITDA as a subtotal), `ebit` computed this way was checked
  against that reported subtotal minus D&A and matches exactly — this is the
  same derivation the years that don't report the subtotal use, cross-checked
  on the two years that do.
- `ebitda` = `ebit` + `depreciation_amortization`.
- `tax_expense` = Current tax + Deferred tax, as reported.
- `net_profit` = Profit for the year, as reported (excludes Other
  Comprehensive Income, which Ind AS reports separately below it).
- `total_assets` = Total assets, as reported on the Balance Sheet.
- `total_debt` = interest-bearing **Borrowings** only (the current-liabilities
  line), excluding lease liabilities (Ind AS 116, first appearing FY2019-20).
  Gulf Oil has carried no non-current/long-term borrowings in any of the ten
  years — every year's short-term working-capital borrowings line is the
  entire debt figure, confirmed by the FY2023-24 auditor's report itself
  ("the Company has not obtained any term loans").
- `cash_and_equivalents` = the **Cash Flow Statement's** "Cash and Cash
  Equivalents at the end of the year" line, not the Balance Sheet's own cash
  line. For FY2016-17 onward (Ind AS) these two agree exactly, since Ind AS
  splits "Cash and cash equivalents" from "Other bank balances" as separate
  Balance Sheet lines. For FY2014-15/FY2015-16 (pre-Ind AS), the Balance
  Sheet's single "Cash and Bank Balances" line is broader than the Cash Flow
  Statement's narrower cash-equivalents figure (it includes some term
  deposits not counted as equivalents) — the Cash Flow Statement figure is
  used both years, for a comparable definition across the accounting-standard
  transition.
- `net_working_capital` = (Total current assets − cash_and_equivalents −
  other bank balances, where separately disclosed) − (Total current
  liabilities − total_debt). This nets financing items (cash, debt) out of
  working capital, which is the convention the forward DCF (Day 4) needs for
  a "change in NWC" cash-flow adjustment that isn't polluted by treasury
  management decisions.
- `capex` = "Purchase of [Fixed Assets / Property, Plant and Equipment],
  including Capital work in progress" from the Cash Flow Statement's
  investing activities, stored as a positive magnitude (the statement itself
  shows it as a cash outflow).
- `shares_outstanding` = number of equity shares issued and fully paid-up at
  fiscal year-end, from the Share Capital note's reconciliation table.

One structural fact worth flagging for later days rather than burying in a
cell: **FY2014-15 is not a normal "first year of the series," it's the first
year this legal entity existed with real operations.** Gulf Oil Lubricants
India Limited was until mid-2014 a shell company (then named Hinduja
Infrastructure Limited); the lubricants business was transferred into it via
a Scheme of Arrangement from Gulf Oil Corporation Limited effective FY2014-15,
which is why that year's own comparative column (FY2013-14) is essentially
zero. The business itself is older than ten years; this listed entity's own
financial history is not. Day 5/6's implied-growth analysis should treat
FY2014-15→FY2015-16 growth with that in mind rather than as organic
year-one-to-year-two growth.

## Citation ledger

One row per figure, `fiscal_year` and `line_item` matching
`data/GULFOILLUB/financials.csv` exactly. Page numbers are **PDF page
numbers** (1-indexed, as any PDF reader counts them), not the document's
printed folio — the two diverge because of cover pages and section resets,
and the PDF page number is unambiguous to reproduce by opening the same
file. Rows marked "derived" are computed from other cited cells per the
methodology section above, not independently sourced — see that section for
the formula, not a page number.

<!-- LEDGER:START -->
| fiscal_year | line_item | value | document | page |
|---|---|---|---|---|
| FY2014-15 | revenue | 96748.17 | Gulf Oil Lubricants India — Annual Report 2014-15 (gulfoilltd.com IR archive) | PDF p.65 |
| FY2014-15 | ebitda | 13861.35 | _derived — see methodology section above_ | — |
| FY2014-15 | depreciation_amortization | 482.12 | Gulf Oil Lubricants India — Annual Report 2014-15 (gulfoilltd.com IR archive) | PDF p.65 |
| FY2014-15 | ebit | 13379.23 | _derived — see methodology section above_ | — |
| FY2014-15 | interest_expense | 1775.35 | Gulf Oil Lubricants India — Annual Report 2014-15 (gulfoilltd.com IR archive) | PDF p.65 |
| FY2014-15 | tax_expense | 3862.92 | Gulf Oil Lubricants India — Annual Report 2014-15 (gulfoilltd.com IR archive) | PDF p.65 |
| FY2014-15 | net_profit | 7740.96 | Gulf Oil Lubricants India — Annual Report 2014-15 (gulfoilltd.com IR archive) | PDF p.65 |
| FY2014-15 | total_assets | 56450.95 | Gulf Oil Lubricants India — Annual Report 2014-15 (gulfoilltd.com IR archive) | PDF p.64 |
| FY2014-15 | total_debt | 21562.75 | Gulf Oil Lubricants India — Annual Report 2014-15 (gulfoilltd.com IR archive) | PDF p.64 |
| FY2014-15 | cash_and_equivalents | 15229.39 | Gulf Oil Lubricants India — Annual Report 2014-15 (gulfoilltd.com IR archive) | PDF p.66 |
| FY2014-15 | net_working_capital | 14797.06 | _derived — see methodology section above_ | — |
| FY2014-15 | capex | 3545.52 | Gulf Oil Lubricants India — Annual Report 2014-15 (gulfoilltd.com IR archive) | PDF p.66 |
| FY2014-15 | shares_outstanding | 49572490 | Gulf Oil Lubricants India — Annual Report 2014-15 (gulfoilltd.com IR archive) | PDF p.72 |
| FY2015-16 | revenue | 101135.42 | Gulf Oil Lubricants India — Annual Report 2015-16 (gulfoilltd.com IR archive) | PDF p.83 |
| FY2015-16 | ebitda | 17709.33 | _derived — see methodology section above_ | — |
| FY2015-16 | depreciation_amortization | 604.15 | Gulf Oil Lubricants India — Annual Report 2015-16 (gulfoilltd.com IR archive) | PDF p.83 |
| FY2015-16 | ebit | 17105.18 | _derived — see methodology section above_ | — |
| FY2015-16 | interest_expense | 1778.92 | Gulf Oil Lubricants India — Annual Report 2015-16 (gulfoilltd.com IR archive) | PDF p.83 |
| FY2015-16 | tax_expense | 5294.79 | Gulf Oil Lubricants India — Annual Report 2015-16 (gulfoilltd.com IR archive) | PDF p.83 |
| FY2015-16 | net_profit | 10031.47 | Gulf Oil Lubricants India — Annual Report 2015-16 (gulfoilltd.com IR archive) | PDF p.83 |
| FY2015-16 | total_assets | 64859.18 | Gulf Oil Lubricants India — Annual Report 2015-16 (gulfoilltd.com IR archive) | PDF p.82 |
| FY2015-16 | total_debt | 19471.91 | Gulf Oil Lubricants India — Annual Report 2015-16 (gulfoilltd.com IR archive) | PDF p.82 |
| FY2015-16 | cash_and_equivalents | 18810.41 | Gulf Oil Lubricants India — Annual Report 2015-16 (gulfoilltd.com IR archive) | PDF p.84 |
| FY2015-16 | net_working_capital | 14096.95 | _derived — see methodology section above_ | — |
| FY2015-16 | capex | 1846.5 | Gulf Oil Lubricants India — Annual Report 2015-16 (gulfoilltd.com IR archive) | PDF p.84 |
| FY2015-16 | shares_outstanding | 49572490 | Gulf Oil Lubricants India — Annual Report 2015-16 (gulfoilltd.com IR archive) | PDF p.91 |
| FY2016-17 | revenue | 108679.27 | BS/PL/CF: Annual Report 2017-18 comparative column (gulfoilltd.com IR archive); shares: Annual Report 2016-17, own report (gulfoilltd.com IR archive) | PDF p.97 |
| FY2016-17 | ebitda | 19815.72 | _derived — see methodology section above_ | — |
| FY2016-17 | depreciation_amortization | 725.04 | BS/PL/CF: Annual Report 2017-18 comparative column (gulfoilltd.com IR archive); shares: Annual Report 2016-17, own report (gulfoilltd.com IR archive) | PDF p.97 |
| FY2016-17 | ebit | 19090.68 | _derived — see methodology section above_ | — |
| FY2016-17 | interest_expense | 982.48 | BS/PL/CF: Annual Report 2017-18 comparative column (gulfoilltd.com IR archive); shares: Annual Report 2016-17, own report (gulfoilltd.com IR archive) | PDF p.97 |
| FY2016-17 | tax_expense | 6352.68 | BS/PL/CF: Annual Report 2017-18 comparative column (gulfoilltd.com IR archive); shares: Annual Report 2016-17, own report (gulfoilltd.com IR archive) | PDF p.97 |
| FY2016-17 | net_profit | 11755.52 | BS/PL/CF: Annual Report 2017-18 comparative column (gulfoilltd.com IR archive); shares: Annual Report 2016-17, own report (gulfoilltd.com IR archive) | PDF p.97 |
| FY2016-17 | total_assets | 73821.56 | BS/PL/CF: Annual Report 2017-18 comparative column (gulfoilltd.com IR archive); shares: Annual Report 2016-17, own report (gulfoilltd.com IR archive) | PDF p.96 |
| FY2016-17 | total_debt | 17848.87 | BS/PL/CF: Annual Report 2017-18 comparative column (gulfoilltd.com IR archive); shares: Annual Report 2016-17, own report (gulfoilltd.com IR archive) | PDF p.96 |
| FY2016-17 | cash_and_equivalents | 25286.22 | BS/PL/CF: Annual Report 2017-18 comparative column (gulfoilltd.com IR archive); shares: Annual Report 2016-17, own report (gulfoilltd.com IR archive) | PDF p.98 |
| FY2016-17 | net_working_capital | 8814.65 | _derived — see methodology section above_ | — |
| FY2016-17 | capex | 4175.54 | BS/PL/CF: Annual Report 2017-18 comparative column (gulfoilltd.com IR archive); shares: Annual Report 2016-17, own report (gulfoilltd.com IR archive) | PDF p.98 |
| FY2016-17 | shares_outstanding | 49633790 | BS/PL/CF: Annual Report 2017-18 comparative column (gulfoilltd.com IR archive); shares: Annual Report 2016-17, own report (gulfoilltd.com IR archive) | PDF p.97 |
| FY2017-18 | revenue | 133225.95 | Gulf Oil Lubricants India — Annual Report 2017-18 (gulfoilltd.com IR archive) | PDF p.97 |
| FY2017-18 | ebitda | 26182.05 | _derived — see methodology section above_ | — |
| FY2017-18 | depreciation_amortization | 1043.31 | Gulf Oil Lubricants India — Annual Report 2017-18 (gulfoilltd.com IR archive) | PDF p.97 |
| FY2017-18 | ebit | 25138.74 | _derived — see methodology section above_ | — |
| FY2017-18 | interest_expense | 853.13 | Gulf Oil Lubricants India — Annual Report 2017-18 (gulfoilltd.com IR archive) | PDF p.97 |
| FY2017-18 | tax_expense | 8429.91 | Gulf Oil Lubricants India — Annual Report 2017-18 (gulfoilltd.com IR archive) | PDF p.97 |
| FY2017-18 | net_profit | 15855.7 | Gulf Oil Lubricants India — Annual Report 2017-18 (gulfoilltd.com IR archive) | PDF p.97 |
| FY2017-18 | total_assets | 102892.77 | Gulf Oil Lubricants India — Annual Report 2017-18 (gulfoilltd.com IR archive) | PDF p.96 |
| FY2017-18 | total_debt | 24806.37 | Gulf Oil Lubricants India — Annual Report 2017-18 (gulfoilltd.com IR archive) | PDF p.96 |
| FY2017-18 | cash_and_equivalents | 32101.37 | Gulf Oil Lubricants India — Annual Report 2017-18 (gulfoilltd.com IR archive) | PDF p.98 |
| FY2017-18 | net_working_capital | 12502.47 | _derived — see methodology section above_ | — |
| FY2017-18 | capex | 10787.02 | Gulf Oil Lubricants India — Annual Report 2017-18 (gulfoilltd.com IR archive) | PDF p.98 |
| FY2017-18 | shares_outstanding | 49699905 | Gulf Oil Lubricants India — Annual Report 2017-18 (gulfoilltd.com IR archive) | PDF p.114 |
| FY2018-19 | revenue | 170579.63 | Gulf Oil Lubricants India — Annual Report 2018-19 (BSE India corporate filings, scrip 538567, since not listed on gulfoilltd.com's own IR archive) | PDF p.108 |
| FY2018-19 | ebitda | 31259.25 | _derived — see methodology section above_ | — |
| FY2018-19 | depreciation_amortization | 2236.48 | Gulf Oil Lubricants India — Annual Report 2018-19 (BSE India corporate filings, scrip 538567, since not listed on gulfoilltd.com's own IR archive) | PDF p.108 |
| FY2018-19 | ebit | 29022.77 | _derived — see methodology section above_ | — |
| FY2018-19 | interest_expense | 1515.55 | Gulf Oil Lubricants India — Annual Report 2018-19 (BSE India corporate filings, scrip 538567, since not listed on gulfoilltd.com's own IR archive) | PDF p.108 |
| FY2018-19 | tax_expense | 9728.99 | Gulf Oil Lubricants India — Annual Report 2018-19 (BSE India corporate filings, scrip 538567, since not listed on gulfoilltd.com's own IR archive) | PDF p.108 |
| FY2018-19 | net_profit | 17778.23 | Gulf Oil Lubricants India — Annual Report 2018-19 (BSE India corporate filings, scrip 538567, since not listed on gulfoilltd.com's own IR archive) | PDF p.108 |
| FY2018-19 | total_assets | 114247.0 | Gulf Oil Lubricants India — Annual Report 2018-19 (BSE India corporate filings, scrip 538567, since not listed on gulfoilltd.com's own IR archive) | PDF p.107 |
| FY2018-19 | total_debt | 28310.81 | Gulf Oil Lubricants India — Annual Report 2018-19 (BSE India corporate filings, scrip 538567, since not listed on gulfoilltd.com's own IR archive) | PDF p.107 |
| FY2018-19 | cash_and_equivalents | 28670.99 | Gulf Oil Lubricants India — Annual Report 2018-19 (BSE India corporate filings, scrip 538567, since not listed on gulfoilltd.com's own IR archive) | PDF p.109 |
| FY2018-19 | net_working_capital | 29306.58 | _derived — see methodology section above_ | — |
| FY2018-19 | capex | 4930.99 | Gulf Oil Lubricants India — Annual Report 2018-19 (BSE India corporate filings, scrip 538567, since not listed on gulfoilltd.com's own IR archive) | PDF p.109 |
| FY2018-19 | shares_outstanding | 49797272 | Gulf Oil Lubricants India — Annual Report 2018-19 (BSE India corporate filings, scrip 538567, since not listed on gulfoilltd.com's own IR archive) | PDF p.124 |
| FY2019-20 | revenue | 164350.07 | Gulf Oil Lubricants India — Annual Report 2019-20 (gulfoilltd.com IR archive) | PDF p.119 |
| FY2019-20 | ebitda | 32207.64 | _derived — see methodology section above_ | — |
| FY2019-20 | depreciation_amortization | 3270.44 | Gulf Oil Lubricants India — Annual Report 2019-20 (gulfoilltd.com IR archive) | PDF p.119 |
| FY2019-20 | ebit | 28937.2 | _derived — see methodology section above_ | — |
| FY2019-20 | interest_expense | 2483.17 | Gulf Oil Lubricants India — Annual Report 2019-20 (gulfoilltd.com IR archive) | PDF p.119 |
| FY2019-20 | tax_expense | 6201.87 | Gulf Oil Lubricants India — Annual Report 2019-20 (gulfoilltd.com IR archive) | PDF p.119 |
| FY2019-20 | net_profit | 20252.16 | Gulf Oil Lubricants India — Annual Report 2019-20 (gulfoilltd.com IR archive) | PDF p.119 |
| FY2019-20 | total_assets | 144654.74 | Gulf Oil Lubricants India — Annual Report 2019-20 (gulfoilltd.com IR archive) | PDF p.118 |
| FY2019-20 | total_debt | 35371.93 | Gulf Oil Lubricants India — Annual Report 2019-20 (gulfoilltd.com IR archive) | PDF p.118 |
| FY2019-20 | cash_and_equivalents | 54582.58 | Gulf Oil Lubricants India — Annual Report 2019-20 (gulfoilltd.com IR archive) | PDF p.121 |
| FY2019-20 | net_working_capital | 27568.15 | _derived — see methodology section above_ | — |
| FY2019-20 | capex | 1833.76 | Gulf Oil Lubricants India — Annual Report 2019-20 (gulfoilltd.com IR archive) | PDF p.121 |
| FY2019-20 | shares_outstanding | 50105710 | Gulf Oil Lubricants India — Annual Report 2019-20 (gulfoilltd.com IR archive) | PDF p.135 |
| FY2020-21 | revenue | 165220.51 | Gulf Oil Lubricants India — Annual Report 2020-21 (gulfoilltd.com IR archive) | PDF p.129 |
| FY2020-21 | ebitda | 31724.61 | _derived — see methodology section above_ | — |
| FY2020-21 | depreciation_amortization | 3386.93 | Gulf Oil Lubricants India — Annual Report 2020-21 (gulfoilltd.com IR archive) | PDF p.129 |
| FY2020-21 | ebit | 28337.68 | _derived — see methodology section above_ | — |
| FY2020-21 | interest_expense | 1463.63 | Gulf Oil Lubricants India — Annual Report 2020-21 (gulfoilltd.com IR archive) | PDF p.129 |
| FY2020-21 | tax_expense | 6865.47 | Gulf Oil Lubricants India — Annual Report 2020-21 (gulfoilltd.com IR archive) | PDF p.129 |
| FY2020-21 | net_profit | 20008.58 | Gulf Oil Lubricants India — Annual Report 2020-21 (gulfoilltd.com IR archive) | PDF p.129 |
| FY2020-21 | total_assets | 144553.0 | Gulf Oil Lubricants India — Annual Report 2020-21 (gulfoilltd.com IR archive) | PDF p.128 |
| FY2020-21 | total_debt | 19794.95 | Gulf Oil Lubricants India — Annual Report 2020-21 (gulfoilltd.com IR archive) | PDF p.128 |
| FY2020-21 | cash_and_equivalents | 49160.86 | Gulf Oil Lubricants India — Annual Report 2020-21 (gulfoilltd.com IR archive) | PDF p.131 |
| FY2020-21 | net_working_capital | 27963.91 | _derived — see methodology section above_ | — |
| FY2020-21 | capex | 859.7 | Gulf Oil Lubricants India — Annual Report 2020-21 (gulfoilltd.com IR archive) | PDF p.131 |
| FY2020-21 | shares_outstanding | 50309527 | Gulf Oil Lubricants India — Annual Report 2020-21 (gulfoilltd.com IR archive) | PDF p.145 |
| FY2021-22 | revenue | 219163.88 | Gulf Oil Lubricants India — Annual Report 2021-22 (gulfoilltd.com IR archive) | PDF p.143 |
| FY2021-22 | ebitda | 32967.56 | _derived — see methodology section above_ | — |
| FY2021-22 | depreciation_amortization | 3571.93 | Gulf Oil Lubricants India — Annual Report 2021-22 (gulfoilltd.com IR archive) | PDF p.143 |
| FY2021-22 | ebit | 29395.63 | _derived — see methodology section above_ | — |
| FY2021-22 | interest_expense | 961.86 | Gulf Oil Lubricants India — Annual Report 2021-22 (gulfoilltd.com IR archive) | PDF p.143 |
| FY2021-22 | tax_expense | 7326.17 | Gulf Oil Lubricants India — Annual Report 2021-22 (gulfoilltd.com IR archive) | PDF p.143 |
| FY2021-22 | net_profit | 21107.6 | Gulf Oil Lubricants India — Annual Report 2021-22 (gulfoilltd.com IR archive) | PDF p.143 |
| FY2021-22 | total_assets | 179242.14 | Gulf Oil Lubricants India — Annual Report 2021-22 (gulfoilltd.com IR archive) | PDF p.142 |
| FY2021-22 | total_debt | 35699.83 | Gulf Oil Lubricants India — Annual Report 2021-22 (gulfoilltd.com IR archive) | PDF p.142 |
| FY2021-22 | cash_and_equivalents | 54873.06 | Gulf Oil Lubricants India — Annual Report 2021-22 (gulfoilltd.com IR archive) | PDF p.145 |
| FY2021-22 | net_working_capital | 51861.76 | _derived — see methodology section above_ | — |
| FY2021-22 | capex | 2460.59 | Gulf Oil Lubricants India — Annual Report 2021-22 (gulfoilltd.com IR archive) | PDF p.145 |
| FY2021-22 | shares_outstanding | 50427273 | Gulf Oil Lubricants India — Annual Report 2021-22 (gulfoilltd.com IR archive) | PDF p.162 |
| FY2022-23 | revenue | 299910.02 | Gulf Oil Lubricants India — Annual Report 2022-23 (gulfoilltd.com IR archive, filed as 'Gulf_Oil_AR_2023_C2C_Design') | PDF p.165 |
| FY2022-23 | ebitda | 38995.72 | _derived — see methodology section above_ | — |
| FY2022-23 | depreciation_amortization | 3961.29 | Gulf Oil Lubricants India — Annual Report 2022-23 (gulfoilltd.com IR archive, filed as 'Gulf_Oil_AR_2023_C2C_Design') | PDF p.165 |
| FY2022-23 | ebit | 35034.43 | _derived — see methodology section above_ | — |
| FY2022-23 | interest_expense | 3764.03 | Gulf Oil Lubricants India — Annual Report 2022-23 (gulfoilltd.com IR archive, filed as 'Gulf_Oil_AR_2023_C2C_Design') | PDF p.165 |
| FY2022-23 | tax_expense | 8040.41 | Gulf Oil Lubricants India — Annual Report 2022-23 (gulfoilltd.com IR archive, filed as 'Gulf_Oil_AR_2023_C2C_Design') | PDF p.165 |
| FY2022-23 | net_profit | 23229.99 | Gulf Oil Lubricants India — Annual Report 2022-23 (gulfoilltd.com IR archive, filed as 'Gulf_Oil_AR_2023_C2C_Design') | PDF p.165 |
| FY2022-23 | total_assets | 207157.15 | Gulf Oil Lubricants India — Annual Report 2022-23 (gulfoilltd.com IR archive, filed as 'Gulf_Oil_AR_2023_C2C_Design') | PDF p.164 |
| FY2022-23 | total_debt | 33158.32 | Gulf Oil Lubricants India — Annual Report 2022-23 (gulfoilltd.com IR archive, filed as 'Gulf_Oil_AR_2023_C2C_Design') | PDF p.164 |
| FY2022-23 | cash_and_equivalents | 65036.0 | Gulf Oil Lubricants India — Annual Report 2022-23 (gulfoilltd.com IR archive, filed as 'Gulf_Oil_AR_2023_C2C_Design') | PDF p.167 |
| FY2022-23 | net_working_capital | 50111.89 | _derived — see methodology section above_ | — |
| FY2022-23 | capex | 2318.32 | Gulf Oil Lubricants India — Annual Report 2022-23 (gulfoilltd.com IR archive, filed as 'Gulf_Oil_AR_2023_C2C_Design') | PDF p.167 |
| FY2022-23 | shares_outstanding | 49017086 | Gulf Oil Lubricants India — Annual Report 2022-23 (gulfoilltd.com IR archive, filed as 'Gulf_Oil_AR_2023_C2C_Design') | PDF p.184 |
| FY2023-24 | revenue | 328409.68 | Gulf Oil Lubricants India — Annual Report 2023-24 (gulfoilltd.com IR archive) | PDF p.184 |
| FY2023-24 | ebitda | 48583.9 | _derived — see methodology section above_ | — |
| FY2023-24 | depreciation_amortization | 4677.45 | Gulf Oil Lubricants India — Annual Report 2023-24 (gulfoilltd.com IR archive) | PDF p.184 |
| FY2023-24 | ebit | 43906.45 | _derived — see methodology section above_ | — |
| FY2023-24 | interest_expense | 2560.94 | Gulf Oil Lubricants India — Annual Report 2023-24 (gulfoilltd.com IR archive) | PDF p.184 |
| FY2023-24 | tax_expense | 10535.66 | Gulf Oil Lubricants India — Annual Report 2023-24 (gulfoilltd.com IR archive) | PDF p.184 |
| FY2023-24 | net_profit | 30809.85 | Gulf Oil Lubricants India — Annual Report 2023-24 (gulfoilltd.com IR archive) | PDF p.184 |
| FY2023-24 | total_assets | 230449.91 | Gulf Oil Lubricants India — Annual Report 2023-24 (gulfoilltd.com IR archive) | PDF p.183 |
| FY2023-24 | total_debt | 32931.01 | Gulf Oil Lubricants India — Annual Report 2023-24 (gulfoilltd.com IR archive) | PDF p.183 |
| FY2023-24 | cash_and_equivalents | 70223.75 | Gulf Oil Lubricants India — Annual Report 2023-24 (gulfoilltd.com IR archive) | PDF p.186 |
| FY2023-24 | net_working_capital | 47469.15 | _derived — see methodology section above_ | — |
| FY2023-24 | capex | 2191.05 | Gulf Oil Lubricants India — Annual Report 2023-24 (gulfoilltd.com IR archive) | PDF p.186 |
| FY2023-24 | shares_outstanding | 49168433 | Gulf Oil Lubricants India — Annual Report 2023-24 (gulfoilltd.com IR archive) | PDF p.205 |
<!-- LEDGER:END -->
