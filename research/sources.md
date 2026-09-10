# Day 2 — sourcing status: BLOCKED

**Scope for today (per `NEXT_STEPS.md` Day 2):** hand-enter ten years of Gulf Oil
Lubricants India (NSE: GULFOILLUB) financials into `data/GULFOILLUB/financials.csv`,
every figure cited to a document and page in this file.

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
