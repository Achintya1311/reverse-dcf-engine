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

## Citation ledger (empty until sourcing unblocks)

One row per figure once transcription starts. `fiscal_year` and `line_item`
must match `data/GULFOILLUB/financials.csv` exactly.

| fiscal_year | line_item | value | document | page |
|---|---|---|---|---|
| _(none yet)_ | | | | |
