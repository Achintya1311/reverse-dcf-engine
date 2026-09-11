# Reverse DCF engine

Takes a share price as given and solves for the growth, margin and reinvestment the market must already believe — then asks whether those assumptions are plausible.

**Status:** Last checkpoint 2026-09-11 · Next: Day 4 - forward FCFF DCF engine, fully parameterized (dcf/forward.py), no hardcoded numbers inside formulas

## What this is

A forward DCF lets you reverse-engineer whatever answer you had already decided on, usually by nudging the terminal growth rate. This does the opposite. The price is the input; the assumptions are the output.

The deliverable is not the solver. It is a two-page write-up saying what the market believes and whether I believe it, with the implied figures set against the company's own ten-year history and its closest peers.

## Correctness gate

The reverse solver round-trips: feed the implied assumptions back through the forward DCF and the current price reproduces within tolerance.

This is the test that decides whether the repo is finished. A result that has not passed it is a draft.

## Data sources

Every source is free. Nothing in this project requires a paid tier, a subscription, or a funded account.

- NSE / BSE filings and annual reports - ten years of financials, hand-entered and cited to page
- Damodaran Online (NYU Stern) - India equity risk premium and industry betas, updated annually
- FRED / RBI - risk-free rate

## How to run

```bash
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
python -m reverse_dcf.solve --ticker EXAMPLE.NS --price 1234.50
python -m reverse_dcf.wacc                         # Day 3: WACC assumptions block for Gulf Oil
python -m reverse_dcf.forward --growth 0.10 --years 10   # Day 4: forward FCFF DCF at an assumed growth rate
```

Runs offline against committed fixtures by default. Live data needs a key in `.env` (see `.env.example`); the fixture path is the default so nothing blocks on network access. `reverse_dcf.wacc` reads its Damodaran/FRED inputs from `fixtures/wacc/*.csv`, committed CSVs - refreshing them from live sources needs `scripts/fetch_wacc_inputs.py`, which is not on the module's runtime path. `reverse_dcf.forward` takes `--growth` explicitly (it has no honest default - that is the number Day 5's solver exists to find) and derives every other assumption (EBIT margin, reinvestment rate, tax rate, WACC, terminal growth) from the latest fiscal year in `data/GULFOILLUB/financials.csv` and Day 3's WACC module; `--margin` and `--reinvestment-rate` override the derived defaults for sensitivity checks.

## Findings

Nothing on the valuation itself yet. Day 1 shortlisted three NSE mid-caps that fit the
₹5,000–50,000 cr / thin-coverage / one-line-business screen and picked Kirloskar Ferrous
Industries to take through the reverse DCF, made by the automated run itself since no live
user was available that day. Achintya reviewed it and asked for a different sector plus
stronger confidence on sourcing ten years of page-cited financials, so the pick changed to
**Gulf Oil Lubricants India** (NSE: GULFOILLUB) — automotive/industrial lubricants, thin
coverage, and a dedicated annual-report archive on its own investor relations site covering
FY2014-15 onward. Full reasoning, the sector-diversity check, and the fallback order are in
[`research/shortlist.md`](research/shortlist.md).

Day 2 transcribed all ten years of standalone financials (`data/GULFOILLUB/financials.csv`,
cited cell-by-cell in `research/sources.md`). Revenue from operations grew from
₹967.5 cr (FY2014-15) to ₹3,284.1 cr (FY2023-24), roughly a 14.5% CAGR over the
window - whether that pace is what today's price already assumes going forward
is exactly what the reverse solver (Day 5) exists to answer, not something to
eyeball here.

Day 4 built the forward FCFF DCF engine (`reverse_dcf/forward.py`) that Day 5's
reverse solver will call inside a root-finder. Revenue grows at a single constant
rate for the explicit forecast, FCFF = EBIT x (1 - tax) x (1 - reinvestment rate),
and a Gordon-growth terminal value picks up everything after. Every number is an
argument or derived from the committed data - the module hardcodes nothing about
Gulf Oil. At the current FY2023-24 base year (13.37% EBIT margin, -15.68%
reinvestment rate - Gulf Oil released working capital and spent less on capex
than it depreciated that year, not a typo, see limitations - 11.61% WACC from
Day 3, 6.89% terminal growth defaulted to the same risk-free rate WACC uses),
a **10% explicit-period revenue growth assumption implies ₹2,294/share**, versus
Day 1's noted ~₹1,140-1,180 actual price at the time of the shortlist - roughly
double. A **5% growth assumption implies ₹1,581/share**, still above the noted
actual price. Neither number is the answer; Day 5's reverse solver exists to find
the growth rate that reproduces today's actual price exactly, not to eyeball it
from a couple of trial runs. Caught and fixed one real bug building this: the
financials CSV is denominated in ₹ lakh while `shares_outstanding` is a raw share
count, so the first version of `implied_share_price` came out three orders of
magnitude too small (₹0.02/share) - `LAKH_TO_RUPEES` now converts at the one
place real data enters the engine, and a regression test bounds the implied price
to a plausible order of magnitude so this can't silently reappear. 17 new tests,
42/42 pass.

Day 3 built the WACC module (`reverse_dcf/wacc.py`). Gulf Oil Lubricants India is
Damodaran's own `Chemical (Basic)` industry classification (`indname.xls`, not a
guess from the lubricants business description); its India-industry unlevered beta
(0.7153) relevers to 0.8041 against Gulf Oil's own FY2023-24 leverage and tax rate,
giving a CAPM cost of equity of 12.58% off a 6.89% India 10-year G-Sec risk-free
rate and Damodaran's 7.08% India equity risk premium. Cost of debt from the filings
(average FY2022-23/FY2023-24 total debt) is 7.75% pre-tax, 5.78% after Gulf Oil's
own 25.48% effective tax rate. Blended at book weights of 14.29% debt / 85.71%
equity, **WACC = 11.61%**. Full sourcing and methodology in
[`research/wacc_sources.md`](research/wacc_sources.md).

## Checkpoint log

<!-- CHECKPOINTS:START -->
| Date | Commit | What changed | Next |
|------|--------|--------------|------|
| 2026-09-11 | `b2a223a` | Day 3 done: WACC module (reverse_dcf/wacc.py). Damodaran/FRED egress confirmed live again today. Gulf Oil Lubricants India is Damodaran's own 'Chemical (Basic)' classification (indname.xls, not a guess) - its India-industry unlevered beta (0.7153) relevers to 0.8041 against Gulf Oil's own FY2023-24 leverage and tax rate for a 12.58% CAPM cost of equity (6.89% India 10Y G-Sec risk-free + 7.08% Damodaran India ERP). Cost of debt from the filings (avg FY22-23/FY23-24 total debt): 7.75% pre-tax, 5.78% after-tax at Gulf Oil's own 25.48% effective tax rate. Book-value capital structure (14.29% debt/85.71% equity, since the Day 2 schema has no equity column) blends to WACC = 11.61%. Damodaran/FRED fixtures committed to fixtures/wacc/, cited in research/wacc_sources.md, reproducible via scripts/fetch_wacc_inputs.py (not on the runtime path). README limitations section documents the book-vs-market capital structure caveat, the Hamada zero-beta-debt assumption, and FRED's 2-3 month reporting lag. 14 new tests, 25/25 pass. | Day 4 - forward FCFF DCF engine, fully parameterized (dcf/forward.py), no hardcoded numbers inside formulas |
| 2026-09-11 | `7ce6c8b` | Day 2 done: the sandbox's egress allowlist was widened mid-session (per Achintya) to reach india.gulfoilltd.com, screener.in, BSE, Damodaran Online and FRED - confirmed live and unblocked what had been blocked for three straight days. Downloaded and transcribed all ten years (FY2014-15 to FY2023-24) of Gulf Oil Lubricants India's standalone financials into data/GULFOILLUB/financials.csv, every cell cited to a specific PDF and page in research/sources.md's 130-row ledger. Revised the earlier standalone-vs-consolidated call after reading the actual consolidated statements: the company has no subsidiary for 9 of 10 years and acquired its one subsidiary mid-FY2023-24, so standalone throughout avoids a one-year comparability break. ebit/ebitda/net_working_capital are derived by a documented, cross-checked rule; financials.py gained real validation logic (to_numeric, check_ebit_identity); all 8 tests pass. | Day 3 - WACC module: cost of equity from Damodaran India ERP and beta (pages.stern.nyu.edu, now reachable), cost of debt from the filings, capital structure from the balance sheet already in data/GULFOILLUB/financials.csv |
| 2026-09-11 | `e0d7471` | Day 2 still blocked: confirmed via the egress proxy's own status log (not a blind retry) that the block is an organization policy denial (403), matching 09-09/09-10. No PDFs dropped in sources/raw/GULFOILLUB/ either. Used the day to close the one open modeling decision Day 2 left unresolved - prefer consolidated financials per fiscal year, falling back to standalone only where no consolidated statement exists - and tightened the resume note so a future run checks sources/raw/ first instead of re-diagnosing the same policy block a fourth time. No financials entered; no data fabricated. | Day 2 (retry) - once egress can reach india.gulfoilltd.com/investors/annual-reports (or an equivalent primary-source archive) or a human drops the ten annual-report PDFs into sources/raw/GULFOILLUB/, hand-enter Gulf Oil Lubricants India's ten years of consolidated financials (standalone only where no consolidated statement exists) into data/GULFOILLUB/financials.csv, citing every figure to document and page in research/sources.md's citation ledger |
| 2026-09-10 | `a0c78d6` | Day 2 re-blocked (confirmed, not transient): re-tested the same 5 finance hosts plus Google/Wikipedia/archive.org, all rejected the same way - this sandbox's egress is a categorical allowlist (only package-registry hosts reachable), not a finance-specific or flaky block. No financials fabricated. Instead scaffolded the Day 2 output: data/GULFOILLUB/financials.csv (10 fiscal-year rows x 14 line-item columns, every cell PENDING), reverse_dcf/financials.py (schema + pending-cell validator), and tests/test_financials_schema.py (5 tests, all passing) so real figures can drop in without a schema redesign. research/sources.md and README limitations updated with the sharper diagnosis and two concrete resume paths. | Day 2 (retry) - either (a) once the sandbox's network allowlist can reach india.gulfoilltd.com/investors/annual-reports or an equivalent primary-source archive, hand-enter the ten years of Gulf Oil Lubricants India financials into the now-scaffolded data/GULFOILLUB/financials.csv replacing PENDING cells, citing every figure to document and page in research/sources.md's citation ledger, or (b) if a human has dropped the source annual-report PDFs into sources/raw/GULFOILLUB/, transcribe from those local files instead |
| 2026-09-10 | `86fbf8f` | Day 2 blocked: sandbox network egress rejects every external host tried (Gulf Oil's own IR archive, screener.in, moneycontrol, NSE, BSE, Damodaran Online, FRED) via both curl and WebFetch - only WebSearch summaries are reachable, which cannot supply a real annual-report page citation. No financials were entered; fabricating page-cited numbers to fill the gap was rejected as dishonest. research/sources.md documents exactly what was tried and the resume plan; README limitations section updated to say the same. | Day 2 (retry) - once network egress can reach india.gulfoilltd.com/investors/annual-reports (or an equivalent primary-source filing archive), pull the FY2014-15 to FY2023-24 Gulf Oil Lubricants India annual reports and hand-enter ten years of financials into data/GULFOILLUB/financials.csv, every figure cited to document and page in research/sources.md |
| 2026-09-10 | `0b78eba` | Correction: Achintya reviewed the automated Day 1 pick (Kirloskar Ferrous, metals) and asked for a different sector plus stronger sourcing confidence for ten years of page-cited financials. Checked 5 more candidates against the same screen and swapped the pick to Gulf Oil Lubricants India (auto/industrial lubricants, thin coverage, dedicated IR annual-report archive covering FY2014-15 onward). Kirloskar Brothers is the fallback. Day 1's scope (shortlist + pick) is unchanged, only which company. | Day 2 - hand-enter ten years of Gulf Oil Lubricants India financials from annual reports into data/GULFOILLUB/financials.csv, every figure cited to a document and page in research/sources.md |
| 2026-09-09 | `f150767` | Day 1: screened NSE mid-caps against the project's cap/coverage/simplicity criteria using live market-cap and analyst-coverage data pulled today, shortlisted Kirloskar Ferrous Industries, Balaji Amines and Time Technoplast, and picked Kirloskar Ferrous (thinnest coverage, simplest single input-output business, genuinely cyclical history). No live user was available for the 'Achintya picks one' step, so the routine picked and recorded an explicit override/fallback order in research/shortlist.md. | Day 2 - hand-enter ten years of Kirloskar Ferrous financials from annual reports into data/KIRLFER/financials.csv, every figure cited to a document and page in research/sources.md |
<!-- CHECKPOINTS:END -->

## Limitations and what would make me wrong

- Ten years of hand-entered financials is a small sample and a transcription risk. Every figure is cited so it can be checked.
- Implied assumptions are only as good as the WACC. The cost of equity uses a published India ERP rather than a bottom-up estimate.
- The solver assumes a single-stage-plus-terminal structure. A business mid-transition may not be well described by it.
- **Day 2's financials are standalone, not consolidated**, for all ten years -
  a comparability call, not a data-quality one. Gulf Oil Lubricants India had
  no subsidiary for nine of the ten fiscal years; its Consolidated Financial
  Statements only become substantive in FY2023-24, the same year a subsidiary
  was acquired mid-year, so a consolidated FY2023-24 would carry a partial-year
  acquisition discontinuity that standalone-across-all-ten-years avoids. See
  `research/sources.md`'s revised-decision entry for the full reasoning.
- **`ebit`, `ebitda` and `net_working_capital` are derived, not reported
  figures.** Ind AS statements after FY2016-17 don't report an EBITDA
  subtotal, so `ebit` = Profit before tax + Finance costs, and `ebitda` =
  `ebit` + D&A - checked against the two years (FY2014-15, FY2015-16) whose
  P&L does report that subtotal explicitly, where it matches exactly.
  `net_working_capital` nets cash and debt out of current assets/liabilities.
  Every derivation rule is documented once in `research/sources.md`'s
  methodology section and in the `reverse_dcf/financials.py` module docstring,
  rather than re-justified per cell in the citation ledger.
- **FY2014-15 isn't a normal first year.** Gulf Oil Lubricants India Limited
  was a shell company until mid-2014; the lubricants business was transferred
  in via a Scheme of Arrangement that fiscal year, so FY2014-15→FY2015-16
  growth reflects a restructuring, not organic year-one-to-year-two growth.
  Worth remembering when Day 5/6 reads the implied-CAGR trend against history.
- **Two years were sourced off Gulf Oil's own site.** FY2018-19's bound annual
  report isn't listed on `india.gulfoilltd.com`'s own archive (only ancillary
  filings for that year are) - sourced from BSE India's corporate-filings
  mirror instead, cover page confirmed. FY2022-23 is filed under an unrelated
  name (`Gulf_Oil_AR_2023_C2C_Design...pdf`) rather than the usual
  "Annual Report" naming - confirmed by its own cover page before use.
- Ten years of hand-entered financials is still a small sample and a
  transcription risk despite the citation ledger - every figure in
  `data/GULFOILLUB/financials.csv` traces to a specific PDF and page in
  `research/sources.md`, so a reviewer can check any cell against the source.
- **The WACC's capital structure is book value, not market value.** The Day 2
  schema has no book-equity or total-liabilities column, so `capital_structure()`
  approximates equity as `total_assets - total_debt`, folding every non-debt
  liability (trade payables, provisions, deferred tax) into "equity". That
  overstates book equity and therefore understates the debt weight - a real bias,
  not a rounding error. Day 1's shortlist noted an approximate market cap of
  ₹5,600–5,800 cr for Gulf Oil; once Day 5 needs a precise current price for the
  reverse solve anyway, it would be worth rerunning WACC at market weights and
  checking how much the 11.61% figure moves.
- **The relevered beta is a Hamada-formula estimate, not a directly measured
  company beta.** It unlevers Damodaran's `Chemical (Basic)` India industry
  average and relevers it to Gulf Oil's own FY2023-24 debt and tax rate. Hamada
  assumes debt itself carries zero systematic risk, which understates the true
  levered beta for a company whose cost of debt (7.75% pre-tax, see
  `research/wacc_sources.md`) is well above the risk-free rate - Gulf Oil's debt
  isn't actually riskless.
- **The 6.89% risk-free rate lags today.** FRED's India 10-year G-Sec series
  (`INDIRLTLT01STM`) was last updated for 2026-06-01 as of this fetch
  (2026-09-11) - a two-to-three-month reporting lag typical of this series, not
  a stale-data mistake, but a real gap between "the rate used" and "the rate
  today" worth keeping in mind if Indian yields have moved meaningfully since.
- **The forward DCF is single-stage-plus-terminal, and margin/reinvestment
  are frozen at one fiscal year's actuals.** `reverse_dcf/forward.py` grows
  revenue at one constant rate for the whole explicit forecast, then a
  Gordon-growth terminal value at a separate (slower) rate. A business with a
  margin ramp, a capex cycle, or a reinvestment step change isn't well
  described by that shape - this is the README's pre-existing solver
  limitation, now also true of the forward engine underneath it.
- **FY2023-24's reinvestment rate is negative (-15.68%)**, because working
  capital fell and capex was below depreciation that year - real numbers from
  `data/GULFOILLUB/financials.csv`, not a bug. `base_case_from_financials`
  defaults to it anyway since it is the most recent actual; a negative
  reinvestment rate held constant for a 10-year forecast is not obviously a
  sustainable steady state, and is exactly the kind of assumption the
  `--reinvestment-rate` override exists to stress-test. Worth revisiting once
  Day 6 sets the implied figures against Gulf Oil's own multi-year history
  instead of a single year.
- **The module lives at `reverse_dcf/forward.py`, not the `dcf/forward.py`
  path named in `NEXT_STEPS.md`.** Every other day's module lives under
  `reverse_dcf/` (`wacc.py`, `financials.py`); a separate top-level `dcf/`
  package for one file would fragment the layout for no benefit. The Day 4
  output artifact is unchanged, only its path.
- **The implied share price at any single growth assumption is not yet
  validated against a round-trip.** Day 4 only checks that the forward engine
  is internally consistent (it collapses to the textbook Gordon growth value
  when explicit and terminal growth match, see `tests/test_forward.py`) and
  that a plausible base case produces a plausible price. Whether the engine
  can reproduce today's actual price for *some* growth rate - the real
  correctness gate this repo is built around - is Day 5's reverse solver to
  prove.

## Where this sits

Part of a nine-repo research pipeline. Stock Stalker screens the NSE universe; this repo publishes a versioned artifact it reads back:

```json
{
  "valuation": {
    "implied_cagr": 0.14,
    "implied_ebit_margin": 0.22,
    "breakeven_growth": 0.09
  }
}
```

Communication is by file contract, not imports, so either side can be refactored without breaking the other.

## Exam mapping

Series XV ch.10 (valuation principles, DCF), ch.12.6-12.7 (sensitivity, margin of safety)

---

CLI only, by design. No dashboard, no server. Charts and documents are written to `outputs/`.
