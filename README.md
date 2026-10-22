# Reverse DCF engine

Educational research on historical data. Not investment advice. Not a SEBI-registered research analyst.

**Question:** at a given share price, what growth, margin and reinvestment does a textbook-consistent reverse DCF say must be assumed — and is that combination even reachable under the model?
**Method:** derive reinvestment from growth via ROIC (`growth = reinvestment × ROIC`, ROIC fading from the 10-year median realized value to WACC) instead of holding one historical fiscal year's reinvestment rate fixed, then solve for the constant growth rate that reproduces the price. The terminal year now satisfies the same identity at its own (slower) terminal growth, not the explicit period's.
**Finding (v3):** no constant growth rate reproduces the committed price at all — the model's own ceiling is ₹914.55/share (10-year framing) or ₹715.52/share (perpetual framing), both below it, and v3's terminal-value fix *lowers* the 10-year ceiling further from v2's own (overstated) ₹962.08. See "The headline v3 finding" below.
**Chart:** `outputs/tornado.png` — the margin × reinvestment sensitivity tornado.
**Reproduce:** `python -m reverse_dcf.solve`

Takes a share price as given and solves for the growth, margin and reinvestment the market must already believe — then asks whether those assumptions are plausible.

**Status:** v3 (17 Oct 2026): the terminal year now reinvests at a rate consistent with terminal growth itself, not the explicit period's growth (CRITIQUES.md V6/V7, Day 18). v2 (16 Oct 2026): reinvestment is derived from growth via ROIC, not held fixed at one historical fiscal year's rate. Part of a nine-repo equity research pipeline; [STOCKSTALKER](https://github.com/Achintya1311/STOCKSTALKER) is the front door.

*Educational research on historical data. Not investment advice. Not a SEBI-registered research analyst.*

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
- screener.in - free, no login required; current market price (Day 5) and peer companies' realized ten-year sales growth (Day 6)

## How to run

```bash
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
python -m reverse_dcf.wacc                         # Day 3: WACC assumptions block for Gulf Oil
python -m reverse_dcf.forward --growth 0.10 --years 10   # Day 4: forward FCFF DCF at an assumed growth rate
python -m reverse_dcf.solve                         # Day 5: reverse solver against the committed market-price fixture
python -m reverse_dcf.solve --grid                  # ...plus the margin x reinvestment sensitivity grid
python -m reverse_dcf.solve --price 1234.50          # override the fixture with an explicit price
python -m reverse_dcf.solve --contract valuation.json  # integration day: write the v0.7 spine contract as JSON
python -m reverse_dcf.solve --ticker ANY --live-financials --prices-csv <ohlcv.csv> --contract out.json  # Day 23: "reverse DCF lite" for any ticker, yfinance financials + a price CSV instead of GULFOILLUB's own fixtures
python -m reverse_dcf.compare                       # Day 6: implied growth vs. Gulf Oil's own history vs. 3 lubricant peers
python -m reverse_dcf.sensitivity                    # Day 7: tornado chart, outputs/tornado.png
python scripts/render_report_pdf.py                  # Day 8: render REPORT.md to outputs/REPORT.pdf
```

Runs offline against committed fixtures by default; no code in this repo reads an API key or needs one at any day. `reverse_dcf.wacc` reads its Damodaran/FRED inputs from `fixtures/wacc/*.csv`, committed CSVs - refreshing them from live sources needs `scripts/fetch_wacc_inputs.py`, which scrapes with plain, keyless `requests` and is not on the module's runtime path. `reverse_dcf.forward` takes `--growth` explicitly (it has no honest default - that is the number Day 5's solver exists to find) and derives every other assumption (EBIT margin, reinvestment rate, tax rate, WACC, terminal growth) from the latest fiscal year in `data/GULFOILLUB/financials.csv` and Day 3's WACC module; `--margin` and `--reinvestment-rate` override the derived defaults for sensitivity checks. `reverse_dcf.solve` reads its market price from `fixtures/market/<TICKER>.csv` by default (refresh with `scripts/fetch_market_price.py`, also off the runtime path) or takes `--price` directly, and runs `scipy.optimize.brentq` on the forward engine to find the growth rate that reproduces it. `reverse_dcf.compare` reads its peer figures from `fixtures/peers/lubricants.csv` (refresh with `scripts/fetch_peer_comparables.py`, off the runtime path) and sets Day 5's implied growth and breakeven growth against Gulf Oil's own realized ten-year revenue CAGR (computed straight from `data/GULFOILLUB/financials.csv`) and three lubricant/oil peers' realized ten-year revenue CAGR.

## v2: fixing the reinvestment formula

### What v1 got wrong

The forward engine's FCFF formula is `EBIT x (1 - tax) x (1 - reinvestment_rate)`. v1 picked
`reinvestment_rate` by reading Gulf Oil's own latest fiscal year (FY2023-24, -15.68% - net
working capital fell that year, so the historical formula `(capex - D&A + change in NWC) /
NOPAT` goes negative even though the business wasn't disinvesting) and then held that one
number fixed for the entire forecast, regardless of what growth rate the forward engine or
the reverse solver was testing. That silently breaks the fundamental growth identity every
finance textbook (and NISM XV ch.10) builds reinvestment-rate DCF on: `growth = reinvestment_rate
x ROIC`. No real return on invested capital multiplies a *negative* reinvestment rate into
*positive* growth - so v1's own base case (10% forecast growth, -15.68% reinvestment) was
internally inconsistent by construction, not just a conservative assumption. `tests/test_forward.py`
now carries this as a permanent regression test
(`test_base_case_reinvestment_is_now_consistent_with_positive_forecast_growth`), proven
broken first (it genuinely errored, by design, until this fix landed - see `CRITIQUES.md` V1)
and now proven fixed.

### v2: reinvestment = growth ÷ ROIC

v2 (`reverse_dcf/forward.py`: `roic_fade_schedule`, `reinvestment_schedule_from_growth`,
`historical_median_roic`) re-derives reinvestment for *every* growth rate the solver tries,
not just the base case: `reinvestment_rate(year t) = revenue_growth / ROIC(year t)`, where
`ROIC(t)` fades linearly from Gulf Oil's own 10-year **median** realized ROIC (25.89% -
`historical_roic_by_year`, nine fiscal-year observations) at year 1 to a **terminal ROIC**
(WACC + a stated spread, default spread **0** - not a view on Gulf Oil's moat, the generic
textbook assumption that no firm earns an excess return over its cost of capital forever once
competition catches up; PLAN.md rule 4 bars this routine from writing a company-specific
judgment call) by the last explicit year. This satisfies the growth identity *by construction*,
for every year, rather than needing a separate check. Zero growth gives an all-zero
reinvestment schedule (no net new capital needed without growth); `--reinvestment-rate`
still overrides it with a flat V1-style rate for the margin/reinvestment grid and the
tornado's own reinvestment-rate shock, which deliberately test "what if this flat historical
rate persisted" as a separate, simpler scenario.

| | v1 (through Sep 2026) | v2 (16 Oct 2026) | v3 (17 Oct 2026) |
|---|---|---|---|
| Reinvestment rate, explicit years | Fixed at FY2023-24's actual (-15.68%), every year, every growth rate | `growth ÷ ROIC(t)`, ROIC fading 25.89% (median) → 11.61% (WACC + 0 spread) across the forecast | Unchanged from v2 |
| Reinvestment rate, terminal year | Not distinguished from the explicit years (same fixed -15.68%) | Not distinguished from the explicit years — inherited the *last explicit year's* rate, sized for the explicit growth rate, not `terminal_growth` (CRITIQUES.md V6, the bug this version fixes) | `terminal_growth ÷ terminal_ROIC`, its own number, consistent with the terminal year's own (slower) growth |
| Consistent with `growth = reinvestment × ROIC`? | No - fails for any positive growth (the bug) | Yes for the explicit years; no for the terminal year once explicit growth differs from terminal growth | Yes, for every year including the terminal one |
| 10-year implied CAGR at ₹1,061.00/share | **-0.49%** | **Unreachable.** No constant growth rate reproduces ₹1,061; the model's own ceiling is **₹962.08/share** (+0.79% growth) — overstated, see below | **Unreachable, by a wider margin.** Ceiling drops to **₹914.55/share** (+11.61% growth) once the terminal year pays its own reinvestment cost honestly |
| Perpetual breakeven growth at ₹1,061.00/share | **3.52%** | **Unreachable.** Ceiling **₹715.52/share** (growth → WACC, 11.61%) | **Unchanged — ₹715.52/share.** The perpetual model has no separate terminal year (forecast_years=1 collapses explicit and terminal into the same year), so V6's bug never applied to it |
| Price vs. growth shape (10-year) | Monotonically increasing (higher growth always meant a higher price) | Not monotonic for GULFOILLUB's own assumptions - rises then falls, since the old terminal formula let the terminal value fall as the *explicit* reinvestment rate it inherited rose with growth (V7's two-root case); see `reverse_dcf.solve._solve_growth` | Monotonically increasing again, at least across GULFOILLUB's full feasible bracket (−99% to the ROIC-fade schedule's own floor) — the terminal value no longer depends on the explicit growth rate at all, removing the mechanism that caused the hump. V7's defensive tie-break code is unchanged and still runs (not proven monotonic for every ticker/price), but it is not hit by this company's own numbers any more |

### The headline v2 finding: today's price is unreachable, not just "pricing in decline"

v1's "-0.49% implied CAGR" read as "the market is pricing in flat-to-declining revenue" - a
real but soft finding (CRITIQUES.md V2 already flagged it as probably a V1 artifact, since
Q1 FY27 revenue grew 32.5% YoY). v2 is sharper and worse for the bull case: once reinvestment
is forced to scale with growth at a ROIC no better than Gulf Oil's own 10-year median fading to
its cost of capital, **no constant growth rate - positive, negative, or zero - produces a
10-year-model price above ₹962.08/share** (v2's own figure; v3 below revises this ceiling
down further) **or a perpetual-model price above ₹715.52/share.**
Today's actual price (₹1,061.00) exceeds both ceilings. `reverse_dcf.solve.implied_growth`
and `perpetual_breakeven_growth` both raise `PriceUnreachableError` rather than returning a
number pretending otherwise; `solve()` catches it and reports `price_reachable=False` plus
each ceiling (`max_achievable_price_10y`/`_perpetual` and the growth rate that achieves it)
so the CLI, the valuation contract, and `reverse_dcf.compare`'s table all say so honestly
instead of crashing or fabricating a figure. This is reported as a method result only - not a
view on whether Gulf Oil is mispriced (S5): it says what a growth/ROIC-consistent single-stage
forward DCF, with a conservative (spread-zero) terminal ROIC assumption, can and cannot
produce at this company's own historical capital efficiency. A less conservative terminal-ROIC
spread raises the ceiling (a sensitivity worth knowing, not a different base case - see
Limitations), and a bull case resting on margin expansion, a higher sustained ROIC, or a
business mid-transition isn't something this single-stage-plus-terminal structure is built to
capture either way (pre-existing limitation, sharper now that reinvestment responds to growth).

One more V1-era intuition v2 overturns, and v3 leaves overturned (with revised numbers): V1
guaranteed perpetual breakeven growth was always *lower* than the 10-year implied growth (a
longer explicit high-growth window always "cost" more). V2/v3 flip this for any price both
models can still reach -
`tests/test_solve.py::test_perpetual_breakeven_growth_is_higher_than_the_ten_year_implied_growth`
- though v3 shrinks the gap between the two models' zero-growth prices sharply: v2's own
10-year zero-growth price (~₹960) was itself inflated by the terminal-value bug v3 fixes (a
"free" terminal year growing forever with no reinvestment cost at g=0); under v3 the honest
10-year zero-growth price is ~₹662, much closer to the perpetual model's own ~₹649 (unchanged,
since the perpetual model has no separate terminal year for the bug to touch).

### v3: the terminal year pays its own reinvestment cost (CRITIQUES.md V6, V7)

**What v2 still got wrong (V6).** v2 fixed the *explicit* forecast years' reinvestment rate
but left `reverse_dcf.forward.terminal_value` extrapolating the *last explicit year's own
FCFF* forward at `terminal_growth`, unchanged since v1. That last year's FCFF was computed
at a reinvestment rate sized to fund the explicit growth rate `g` — usually much faster than
`terminal_growth` — so growing it forward at the slower `terminal_growth` silently kept paying
the fast-growth reinvestment bill into a perpetuity that was only supposed to need the slow one.
The richer the explicit growth, the worse the mismatch: it is the mechanical reason the 10-year
model's price *fell* once growth rose much past ~1%, even though Gulf Oil's own ROIC
comfortably exceeds WACC (an ROIC above the discount rate should make growth value-accretive,
not value-destructive).

**The fix.** `terminal_value` no longer takes the last explicit year's FCFF; it takes that
year's NOPAT (before reinvestment) and builds a fresh terminal year: grown once more at
`terminal_growth`, reinvested at a *new* `terminal_reinvestment_rate = terminal_growth ÷
terminal_ROIC` — the same growth identity the explicit years already satisfy, now applied at
the terminal year's own (slower) growth rate instead of inheriting the explicit one.
`terminal_growth` itself is capped at the risk-free rate even when a caller overrides it
(Damodaran's convention that a perpetual growth rate cannot outpace the economy forever,
already the unoverridden default), so the terminal year's own growth/reinvestment pair stays
economically admissible. `DcfAssumptions.terminal_reinvestment_rate` is `None` everywhere except
the V2 growth/ROIC schedule — a flat reinvestment-rate override (the CLI's `--reinvestment-rate`,
the sensitivity tornado's and `grid_implied_growth`'s own flat-rate shocks) still means that one
rate holds forever, terminal year included, exactly as before. `tests/test_forward.py`'s
`test_terminal_value_is_continuous_across_the_explicit_terminal_boundary` checks the Day 18
requirement directly: pushing the explicit/terminal split out by one year, at the same terminal
assumptions, cannot move the total value — the split is only an accounting device.

**The result is worse, not better, for the bull case — reported honestly either way (PLAN.md
rule 5).** Fixing the bug *lowers* the 10-year ceiling, from v2's ₹962.08 to **₹914.55** (the
old number was itself inflated by the free lunch this fix removes), widening the gap to today's
₹1,061.00 price from ₹99 to ₹146 short. The perpetual model is untouched (₹715.52, unchanged) —
it has no separate terminal year, since `forecast_years=1` already collapses explicit and
terminal into the same year (`roic_fade_schedule`'s own docstring).

**V7 (the two-root tie-break) is resolved for GULFOILLUB's own numbers, not by changing the
tie-break code.** v2 found price non-monotonic in growth once reinvestment scaled with it,
raising the possibility of two valid roots for the same target price
(`reverse_dcf.solve._solve_growth`'s own defensive probe-and-bisect logic, added to handle
that). Under v3, the terminal value no longer depends on the *explicit* growth rate at all —
only on the fixed `terminal_growth`/`terminal_ROIC` pair — which removes the mechanism that
made price turn down at high growth. Sampling the full feasible bracket for GULFOILLUB's base
case (-99% to the ROIC-fade schedule's own floor, ~11.61%) now shows price rising
monotonically throughout, so no price in that range has two roots any more. `_solve_growth`'s
tie-break code is left in place, deliberately: monotonicity is an empirical property of this
company's own numbers today, not a proof for every ticker, price, or future fiscal year, and
the tie-break is the right fallback if a non-monotonic case ever recurs.

## Findings

Day 8 wrote [`REPORT.md`](REPORT.md), the two-page write-up this whole project exists to
produce, rendered to `outputs/REPORT.pdf` by a new `scripts/render_report_pdf.py`
(plain-text/table typesetting via matplotlib's `PdfPages` - no new dependency, since
matplotlib is already required for Day 7's tornado chart). It states the actual headline
sentence plainly: solved against the ₹1,061.00/share price captured 2026-09-12, the model's
implied growth rate for Gulf Oil is essentially flat-to-declining (-0.49% 10-year implied CAGR,
or 3.52% on the more forgiving perpetual-breakeven framing) - well below Gulf Oil's own
realized 14.54% and below every peer checked. (Superseded by the v2 finding above: under the
growth/ROIC-consistent model, this price is unreachable at any constant growth rate at all -
see "The headline v2 finding" - this paragraph records what v1 found, for the narrative below.) The write-up also does the thing Day 6/7's numbers alone didn't: it
separates the real finding from the modeling noise, since Day 7's own sensitivity grid shows
implied growth ranging -5% to +25% depending which of Gulf Oil's nine historically realized
(margin, reinvestment) year-pairs is assumed to persist - the headline direction survives that
range (even the grid's +25% high end stays under the realized 14.54%), but the exact decimal
should not be read as precise. `scripts/render_report_pdf.py` handles exactly the Markdown
subset `REPORT.md` uses (headers, bullets, pipe tables, blank-line paragraphs, `---` as an
explicit page break) and errors rather than silently mis-rendering anything else; long table
cells are truncated with an ellipsis rather than overflowing the page, trimming only the widest
column in a row so short labels (company names, percentages) stay intact. 10 new tests,
87/87 pass; the CLI run directly, output inspected page-by-page as rendered PNGs to check
for text overlap or clipping before committing.

Nothing else on the valuation itself before this. Day 1 shortlisted three NSE mid-caps that fit the
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

Day 6 set Day 5's implied figures against Gulf Oil's own ten-year realized
history and three lubricant/oil peers (`reverse_dcf/compare.py`,
`python -m reverse_dcf.compare`). The comparison table is the actual
argument this project exists to make: solved against the ₹1,061.00/share
price captured 2026-09-12, the model's **implied 10-year revenue CAGR is
-0.49%** (or, on the more forgiving perpetual-breakeven framing, **3.52%
forever**) - both **well below Gulf Oil's own realized 10-year revenue
CAGR of 14.54%** (computed directly
from `data/GULFOILLUB/financials.csv`, `historical_revenue_cagr()`), and
below **every one of the three lubricant peers checked**: Castrol India
(6.0%), Gandhar Oil Refinery (9.0%, consolidated - its standalone entity's
compounded-sales-growth series is too short for a 10-year figure, the same
kind of standalone-vs-consolidated judgment call Day 2 already had to make
for Gulf Oil itself), and Savita Oil Technologies (11.0%). So the one
sentence this project exists to produce is not "expectations exceed
history" (the contract spec's placeholder) but its mirror image: *the
model's implied growth rate at today's price is essentially
flat-to-declining for Gulf Oil, a bar every comparable lubricant company -
Gulf Oil's own past included - has cleared over the last ten years.* Sourced from
screener.in's free "Compounded Sales Growth" ranges table
(`scripts/fetch_peer_comparables.py`, committed to
`fixtures/peers/lubricants.csv`), the same free-tier, no-login source
`fetch_market_price.py` already uses. As a sanity check, screener's own
10-year figure for Gulf Oil (15%, standalone) is committed alongside the
peers and is close to but not identical with this project's own
14.54% - both trace to the same underlying revenue series, so the ~0.5pt
gap is rounding and a possible small difference in what each source counts
as "revenue" (see limitations), not a data error worth chasing further. 9
new tests, 66/66 pass; the CLI run directly against the default fixture
price and a `--price` override.

Day 5 built the reverse solver (`reverse_dcf/solve.py`): `scipy.optimize.brentq`
on Day 4's forward engine, searching for the constant explicit-period revenue
growth rate that reproduces a given market price. Solving against **today's
actual price (₹1,061/share, screener.in, 2026-09-12)** at the FY2023-24 base
case (13.37% margin, -15.68% reinvestment) gives an **implied 10-year growth
rate of -0.49%** — essentially flat-to-slightly-declining, not growth. That
is a real surprise against Day 2's finding of a ~14.5% ten-year realized
revenue CAGR: the model's implied growth rate at today's price sits *well
below* that realized history, the opposite of the "expectations exceed
history" placeholder in this project's own contract spec — worth treating
as a live finding to interrogate in Day 6, not a mistake to explain away. The price
moved materially even against Day 1's ~₹1,140-1,180 shortlist-day estimate
from three days earlier, so this is one noisy snapshot, not a settled
number — see limitations. A second, more conservative number,
**perpetual breakeven growth of 3.52%**, answers a related question: what
constant growth, held forever with no assumed slowdown, would justify the
price — reusing the exact forecast_years=1/terminal_growth=growth
equivalence `tests/test_forward.py` already proves collapses the forward
engine to the textbook single-stage Gordon growth formula, so it needed no
new pricing method. Both numbers **round-trip**: feeding the solved growth
back through `reverse_dcf.forward.run_dcf` reproduces the target price to
within a paisa, the actual correctness gate this repo is built around
(`tests/test_solve.py`). A grid over all nine year-pairs of Gulf Oil's own
historically realized (margin, reinvestment) combinations shows the implied
growth swinging from about -5% to +25% depending which year's operating
profile is assumed to continue — the single-year base case is not a
robust anchor on its own, which is exactly why Day 6 needs the multi-year
comparison rather than reading this one number in isolation. 14 new tests
(57/57 pass); CLI run directly with the default fixture price, `--grid`,
`--price` override, and the unreachable-target error path all exercised by
hand, not just under pytest.

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

## Limitations and what would make me wrong

- Ten years of hand-entered financials is a small sample and a transcription risk. Every figure is cited so it can be checked.
- Implied assumptions are only as good as the WACC. The cost of equity uses a published India ERP rather than a bottom-up estimate.
- The solver assumes a single-stage-plus-terminal structure. A business mid-transition may not be well described by it.
- **Fixed in v3 (17 Oct 2026, CRITIQUES.md V6): the terminal value no longer extrapolates the
  last explicit year's FCFF forward at `terminal_growth`.** It now builds a fresh terminal
  year (NOPAT grown once more at `terminal_growth`, reinvested at its own
  `terminal_growth / terminal_ROIC`) — see "v3: the terminal year pays its own reinvestment
  cost" above for the full mechanism, the regression test
  (`test_terminal_value_is_continuous_across_the_explicit_terminal_boundary`), and the revised
  ceiling (₹914.55, down from v2's own inflated ₹962.08).
- **The terminal ROIC spread (default 0, i.e. terminal ROIC = WACC) is a generic,
  stated convention, not a company-specific estimate - and the "unreachable at ₹1,061"
  finding is sensitive to it, more so after v3's fix.** Probing spread values directly (not
  committed to any file, reproducible via `roic_spread=` on any `reverse_dcf.solve` function):
  spread 0% → 10-year ceiling ₹914.55 (unreachable); spread 2% → reachable at 11.21% growth;
  spread 5% → reachable at 8.08% growth; spread 10% → reachable at 5.87% growth. v3's fix makes
  reachability flip at a *smaller* spread than v2 reported (v2: still unreachable even at a 10%
  spread, ceiling ₹1,134) — correctly sharper, since v2's own ceiling was itself inflated by the
  bug v3 fixes. A spread that large would be a claim that Gulf Oil keeps a durable
  above-cost-of-capital return forever, which this routine does not assert (PLAN.md rule 4) -
  but a reader who believes that claim would reach a different conclusion than "unreachable."
- **Resolved for GULFOILLUB's own numbers in v3, not by changing the code (CRITIQUES.md V7):**
  `_solve_growth` still carries its defensive two-root tie-break (documented in its own
  docstring), but v3's fix removed the mechanism that made price non-monotonic in growth for
  this company's assumptions — see "v3" above. The tie-break is left in place as a fallback,
  not proven impossible for every ticker or future price.
- **`REPORT.md` (Day 8's write-up) and its rendered `outputs/REPORT.pdf` still quote v1's
  numbers** (-0.49% implied CAGR, 3.52% breakeven) and have not been regenerated against v2 -
  out of scope for `NEXT_STEPS.md`'s Day 4 row (README only); tracked as CRITIQUES.md P14.
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
  `data/GULFOILLUB/financials.csv`, not a bug. ~~`base_case_from_financials`
  defaults to it anyway since it is the most recent actual~~ **(v2 update,
  16 Oct 2026): no longer true.** `base_case_from_financials` now derives
  reinvestment from whatever growth rate is being forecast via
  `reinvestment_schedule_from_growth`, not from this one historical year -
  see "v2: fixing the reinvestment formula" above (CRITIQUES.md V1). The
  -15.68% figure still only matters as the `historical_roic_by_year`/
  `historical_margins_and_reinvestment` input data and as an explicit
  `--reinvestment-rate` override value, same as any other historical year.
- **The module lives at `reverse_dcf/forward.py`, not the `dcf/forward.py`
  path named in `NEXT_STEPS.md`.** Every other day's module lives under
  `reverse_dcf/` (`wacc.py`, `financials.py`); a separate top-level `dcf/`
  package for one file would fragment the layout for no benefit. The Day 4
  output artifact is unchanged, only its path.
- **The market price the reverse solver targets is a single live snapshot,
  not a robust estimate.** `fixtures/market/GULFOILLUB.csv` was fetched from
  screener.in on 2026-09-12 (₹1,061/share) - three days after Day 1's
  shortlist noted ~₹1,140-1,180, already a ~7-9% move. Re-running
  `scripts/fetch_market_price.py` on a different day will move the implied
  growth number, sometimes by more than the underlying investment thesis
  changed. The implied-growth *sign* (flat-to-negative vs. Day 2's realized
  14.5% CAGR) is unlikely to flip on typical daily noise, but the exact
  percentage should not be quoted to two decimal places in the write-up.
- **The base-case margin is frozen at one fiscal year's actual** (reinvestment
  no longer is, as of v2 - see above). `reverse_dcf/solve.py`'s sensitivity
  grid (`--grid`) still deliberately sweeps Gulf Oil's own nine historically
  realized (margin, **flat** reinvestment) year-pairs as a separate,
  simpler "what if this exact historical operating profile, not the growth-
  consistent v2 model, persisted for 10 years" scenario - see its own `n/a`
  cells where a reinvestment rate above 100% puts the target price out of
  reach.
- **The reverse solver no longer assumes one root exists and is unique
  (v2 update, 16 Oct 2026)** - it did under v1, since a monotonic
  fixed-reinvestment price always had at most one crossing of any target
  price in bracket. v2's reinvestment rate grows with the growth rate being
  tested, so price can rise then fall within the bracket; `_solve_growth`
  now checks the bracket's own interior extremum and can face two valid
  roots, not just zero or one (new limitation bullet above, and
  `_solve_growth`'s own docstring).
- **"Implied growth" and "breakeven growth" answer different questions and
  are not the same number by design.** The former assumes 10 years of the
  quoted growth rate followed by a slower terminal decay (matching the
  forward engine's existing shape); the latter assumes the same growth rate
  holds forever with no deceleration at all, so it is always the lower,
  more conservative of the two. Reporting only one of them in Day 8's
  write-up would overstate or understate how demanding the market's
  assumption really is - both belong in the final note.
- **The peer set is three companies, chosen for being recognizable
  lubricant/oil comparables (Castrol India, Savita Oil Technologies, Gandhar
  Oil Refinery), not a systematic screen** the way Day 1 screened candidate
  companies to model. A different reasonable peer set (e.g. Tide Water Oil
  /Veedol, whose screener.in page did not resolve cleanly and was dropped
  rather than guessed at) could show a different range - three points is
  enough to say "Gulf Oil isn't uniquely fast-growing" but not enough for a
  statistical claim.
- **Peer growth figures are screener.in's own "Compounded Sales Growth"
  calculation, not this project's own transcription** - unlike Gulf Oil's
  own financials, no peer got a full Day-2-style hand-entry with page
  citations. That is a deliberate scope choice (transcribing ten years of
  three more companies is its own multi-day project, not a bounded Day 6
  chunk), but it means peer numbers are trusted to a third-party
  aggregator's methodology rather than independently reproduced.
- **Gandhar Oil Refinery's peer figure is its *consolidated* 10-year sales
  CAGR; the other two peers and Gulf Oil itself use *standalone*.**
  Gandhar's standalone entity is too recently restructured for
  screener.in to compute a 10-year standalone figure (blank cell, not a
  wrong number) - consolidated was the only free source with a real
  10-year figure, so it is used and flagged rather than silently mixed in
  as if it were on the same basis as the others.
- **Screener.in's own 10-year sales CAGR for Gulf Oil (15%) and this
  project's own computed figure (14.54%) are close but not identical**,
  both derived from the same underlying reported revenue. The small gap is
  most likely rounding (screener displays whole percent) or a difference in
  exactly which revenue line screener treats as "Sales" versus this
  project's `revenue` column (Day 2's `research/sources.md` documents the
  exact statement line used here) - worth knowing about, not worth
  reconciling to the decimal for a sanity-check row.
- **The round-trip check is now real** (Day 4's version of this limitation
  said it wasn't yet proven): `tests/test_solve.py` feeds every solved
  growth rate back through `reverse_dcf.forward.run_dcf` and asserts the
  target price reproduces to within a paisa. That is the correctness gate
  this repo is built around, not a nice-to-have test.

## Checkpoint log

<!-- CHECKPOINTS:START -->
| Date | Commit | What changed | Next |
|------|--------|--------------|------|
| 2026-10-17 | `8fa8372` | Day 18 done: fixed the terminal-value bug CRITIQUES.md V6 flagged (reopened 17 Oct) -- `terminal_value()` extrapolated the last explicit year's own FCFF forward at `terminal_growth`, but that FCFF was reinvested at a rate sized for the explicit-period growth rate, not `terminal_growth`, breaking `growth = reinvestment_rate x ROIC` exactly at the explicit/terminal boundary. Fix: the terminal year now builds its own FCFF fresh from the last explicit year's NOPAT, reinvested at a new `terminal_reinvestment_rate = terminal_growth / terminal_ROIC` (`terminal_growth` itself capped at the risk-free rate even on override). New `DcfAssumptions.terminal_reinvestment_rate` field; every flat-reinvestment override path (CLI, `grid_implied_growth`, the sensitivity tornado's own shock, `perpetual_breakeven_growth`) resets it to `None`, reproducing the old (correct, for a flat-forever scenario) behaviour exactly. Result: the 10-year ceiling drops from v2's (now-understood-as-inflated) ₹962.08 to ₹914.55 -- worse for the bull case, reported as such. Perpetual model (₹715.52) untouched. V7 (two-root tie-break): sampling the full feasible bracket shows price now rises monotonically throughout for GULFOILLUB's own numbers, since the terminal value no longer depends on the explicit growth rate -- `_solve_growth`'s defensive tie-break code is left in place, not removed, since this isn't proven for every ticker or price. New regression test `test_terminal_value_is_continuous_across_the_explicit_terminal_boundary` (Day 18's own requirement) plus direct tests of the new field's two cases. README's v1/v2/v3 table, the "v3" narrative section and Limitations updated with the new ceilings; valuation contract and STOCKSTALKER's `fixtures/valuation/GULFOILLUB.json` regenerated; the site's reverse-DCF findings card and tornado chart updated to the new ₹915 ceiling. 117/117 tests pass (`PYTHONPATH=. uv run --with-requirements requirements.txt --with pytest pytest`); every changed CLI (`reverse_dcf.solve`, `--grid`, `reverse_dcf.sensitivity`, `reverse_dcf.grill`, `reverse_dcf.compare`) run by hand. | Day 19 - CI where none exists (reverse-dcf-engine, monte-carlo-risk-lab, fama-french-factor-model, three-statement-model) |
| 2026-09-14 | `3659b22` | Integration day: shipped Stock Stalker v0.7 (valuation gate on survivors). reverse_dcf.solve gained a --contract flag wiring the already-tested to_contract() method to the CLI, writing the v0.7 JSON block ({"valuation": {"implied_cagr": -0.49%, "implied_ebit_margin": 13.37%, "implied_reinvestment": -15.68%, "breakeven_growth": 3.52%}}) as a file, never a Python import. On the spine side, STOCKSTALKER's new stockstalker.gates.valuation reads that file and attaches it to the one screen candidate whose ticker matches; report.py's new --valuation-contract/--valuation-ticker flags apply the gate and add two columns to the screen table when populated. Verified honestly, not glossed over: 96/96 reverse-dcf-engine tests pass, 161 STOCKSTALKER tests pass (1 pre-existing live-network test skipped, no network here), and both CLIs were run by hand end to end. The real integration produces zero matches -- GULFOILLUB (the name reverse-dcf-engine actually researched) is not in STOCKSTALKER's 3-ticker fixture universe (RELIANCE/TATACHEM/CROMPTON) -- so the gate logic is proven against a synthetic contract keyed to a universe ticker instead, and both READMEs record the real-data non-match as a limitation rather than hiding it. STOCKSTALKER bumped to v0.7.0 per the hub's release-track versioning (each satellite gets its own version number by pipeline position, not shipping order). Also found and fixed both this repo's and STOCKSTALKER's local main branch stuck in a stale detached HEAD (same issue this repo's own Day 5 log once noted) before committing, so today's push lands on a real branch. | monte-carlo-risk-lab Day 1 - vectorized seeded GBM simulator |
| 2026-09-13 | `3e824f9` | Day 9 done: grilled the Day 8 conclusion with two mechanical robustness checks (reverse_dcf/grill.py), not just prose. (1) Base-year check: recomputing Gulf Oil's realized 10yr CAGR with the flagged FY2014-15 restructuring year dropped as base gives 15.86%, higher than the 14.54% quoted throughout - that flagged year was suppressing the realized-history anchor, not inflating it. (2) Forecast-horizon check: re-solving implied growth from a 5yr to 15yr explicit horizon moves it from -5.79% to +1.28% - a real lever nobody had shocked before - but even at 15yr it stays >13pp below realized growth on either base year. Neither attack broke the headline finding; REPORT.md's new 'Day 9 - attacking the conclusion' section records both results, and forecast horizon was added to the limitations list as a real sensitivity axis. This closes out reverse-dcf-engine's 9-day plan (9/9). 8 new tests (95/95 pass); python -m reverse_dcf.grill run directly against the default price and a --price override; REPORT.md re-rendered to PDF to confirm the longer report still typesets cleanly (page count unchanged). | Integration day - ship Stock Stalker v0.7 (valuation gate on survivors) using reverse-dcf-engine's contract output ({"valuation": {"implied_cagr", "implied_ebit_margin", "implied_reinvestment", "breakeven_growth"}}) |
| 2026-09-13 | `2e4783f` | Day 8 done: REPORT.md, the two-page write-up this project exists to produce, rendered to outputs/REPORT.pdf via new scripts/render_report_pdf.py (matplotlib PdfPages typesetter, no new dependency). States the headline finding plainly: at today's price (Rs1,061.00/share) the market is pricing in essentially flat-to-declining revenue for Gulf Oil (-0.49% 10yr implied CAGR, 3.52% perpetual breakeven) - well below its own realized 14.54% 10-year CAGR and below every peer checked. Separates that finding from Day 7's modeling noise (implied growth ranges -5% to +25% across Gulf Oil's own 9 historically realized margin/reinvestment year-pairs; the headline direction survives that range) rather than reading one decimal as settled - both belong in the write-up. Full limitations section carried through, condensed against README's own rather than duplicated. 10 new tests, 87/87 pass; CLI run directly, PDF output inspected page-by-page as rendered PNGs for text overlap/clipping before committing. | Day 9 - run the grilling skill against the conclusion, then revise what does not survive |
| 2026-09-12 | `7914fe4` | Day 7 done: tornado chart (outputs/tornado.png) for implied-growth sensitivity to the four assumptions Day 5's solver holds fixed (WACC, terminal growth, EBIT margin, reinvestment rate), via new reverse_dcf/sensitivity.py. Each is shocked one at a time and implied growth re-solved at the low/high end. Shock sizes are grounded, not invented: EBIT margin and reinvestment rate use +/-1 std of Gulf Oil's own 9-10yr history (already computed in solve.historical_margins_and_reinvestment); WACC and terminal growth use the standard +/-1pp DCF convention since no equivalent multi-year series exists for either. Reinvestment rate dominates the tornado (12.4pp swing) - Gulf Oil's own reinvestment rate has swung -15% to +100% across capex-light/heavy years, a real volatility, not a shock-size artifact. Added an optional wacc override to solve.implied_growth to make this possible. 11 new tests, 77/77 pass; CLI run directly against the default fixture price and a --price override, chart inspected visually for label collisions. | Day 8 - REPORT.md: what the market believes, and whether it holds up, with a limitations section, rendered to PDF |
| 2026-09-12 | `dbea264` | Day 6 done: set Day 5's implied growth (-0.49% 10yr, 3.52% perpetual breakeven) against Gulf Oil's own realized 10-year revenue CAGR (14.54%, computed straight from data/GULFOILLUB/financials.csv) and 3 lubricant/oil peers' realized 10-year sales growth (Castrol India 6%, Gandhar Oil Refinery 9% consolidated, Savita Oil Technologies 11%), all via new reverse_dcf/compare.py and scripts/fetch_peer_comparables.py against screener.in's free ranges tables, committed to fixtures/peers/lubricants.csv. The comparison table is the project's actual argument: at today's price the market's implied growth sits below every peer's realized growth and well below Gulf Oil's own history - the mirror image of the contract spec's 'expectations exceed history' placeholder. Screener's own 10yr figure for Gulf Oil (15%) committed alongside as a cross-check, close to but not identical with this project's 14.54% (documented in limitations). Also fast-forwarded both this repo and the hub from a stale detached HEAD before starting. 9 new tests, 66/66 pass; CLI run directly against the default fixture price and a --price override. | Day 7 - sensitivity analysis and tornado chart (outputs/tornado.png) |
| 2026-09-12 | `4bc22cc` | Day 5 done: reverse solver (reverse_dcf/solve.py). scipy.optimize.brentq on Day 4's forward engine finds the constant explicit-period growth rate that reproduces a given market price; every solve round-trips (fed back through run_dcf it reproduces the target price to within a paisa - tests/test_solve.py's version of the repo's 'Done when' gate). Solved against today's live price (Rs1,061/share, screener.in, 2026-09-12, fetched via new scripts/fetch_market_price.py and committed to fixtures/market/GULFOILLUB.csv) at the FY2023-24 base case: implied 10-year growth is -0.49% - essentially flat, well below Day 2's ~14.5% realized 10-year revenue CAGR, the opposite of 'expectations exceed history'. A second number, perpetual breakeven growth (3.52%, reusing test_forward.py's forecast_years=1/terminal_growth=growth Gordon-growth equivalence), gives a more conservative benchmark. Also built grid_implied_growth(), sweeping all nine of Gulf Oil's own historically realized (margin, reinvestment) year-pairs (not invented scenarios) - implied growth ranges roughly -5% to +25% across them, so the single base-case number is not a robust anchor on its own. README findings and limitations sections updated with all of this, including the single-day price-snapshot caveat and the implied-vs-breakeven distinction. Also fast-forwarded a stale local main (repo was left in a detached HEAD matching origin) before starting. 14 new tests, 57/57 pass; CLI run directly with the default fixture price, --grid, --price override, and the unreachable-target-price error path all exercised by hand. | Day 6 - set the implied figures (10-year implied growth, perpetual breakeven growth, and the margin/reinvestment sensitivity grid) against Gulf Oil's own ten-year realized history and two or three peers - a comparison table, the actual argument this project exists to make |
| 2026-09-11 | `c7dbc10` | Day 4 done: forward FCFF DCF engine (reverse_dcf/forward.py, not dcf/forward.py - kept the existing package layout). Revenue grows at a single constant rate, FCFF = EBIT*(1-tax)*(1-reinvestment_rate), Gordon-growth terminal value; every assumption is a parameter, and base_case_from_financials() derives all but growth itself from FY2023-24's actuals plus Day 3's WACC module, so nothing about Gulf Oil is hardcoded in the formulas. Caught and fixed a real bug exercising the CLI: financials.csv is in lakh but shares_outstanding is a raw count, so implied_share_price first came out three orders of magnitude too small (0.02 vs the correct ~2,294) - fixed with a documented LAKH_TO_RUPEES conversion at the one place real data enters the engine, plus a regression test bounding the price to a plausible order of magnitude. At the FY2023-24 base case (13.37% margin, -15.68% reinvestment rate - working capital released, capex below depreciation, a real number not a typo - 11.61% WACC, 6.89% terminal growth), 10% growth implies ~Rs 2,294/share and 5% implies ~Rs 1,581/share against Day 1's noted ~Rs 1,140-1,180 actual price - both above actual, which is exactly what Day 5's reverse solver exists to pin down properly rather than eyeball. 17 new tests, 42/42 pass; CLI run directly (base case, growth overrides, margin/reinvestment overrides, missing --growth, and wacc<=terminal_growth error path all exercised by hand). | Day 5 - reverse solver: scipy.optimize.brentq on growth to match current market cap, then grid over margin and reinvestment |
| 2026-09-11 | `b2a223a` | Day 3 done: WACC module (reverse_dcf/wacc.py). Damodaran/FRED egress confirmed live again today. Gulf Oil Lubricants India is Damodaran's own 'Chemical (Basic)' classification (indname.xls, not a guess) - its India-industry unlevered beta (0.7153) relevers to 0.8041 against Gulf Oil's own FY2023-24 leverage and tax rate for a 12.58% CAPM cost of equity (6.89% India 10Y G-Sec risk-free + 7.08% Damodaran India ERP). Cost of debt from the filings (avg FY22-23/FY23-24 total debt): 7.75% pre-tax, 5.78% after-tax at Gulf Oil's own 25.48% effective tax rate. Book-value capital structure (14.29% debt/85.71% equity, since the Day 2 schema has no equity column) blends to WACC = 11.61%. Damodaran/FRED fixtures committed to fixtures/wacc/, cited in research/wacc_sources.md, reproducible via scripts/fetch_wacc_inputs.py (not on the runtime path). README limitations section documents the book-vs-market capital structure caveat, the Hamada zero-beta-debt assumption, and FRED's 2-3 month reporting lag. 14 new tests, 25/25 pass. | Day 4 - forward FCFF DCF engine, fully parameterized (dcf/forward.py), no hardcoded numbers inside formulas |
| 2026-09-11 | `7ce6c8b` | Day 2 done: the sandbox's egress allowlist was widened mid-session (per Achintya) to reach india.gulfoilltd.com, screener.in, BSE, Damodaran Online and FRED - confirmed live and unblocked what had been blocked for three straight days. Downloaded and transcribed all ten years (FY2014-15 to FY2023-24) of Gulf Oil Lubricants India's standalone financials into data/GULFOILLUB/financials.csv, every cell cited to a specific PDF and page in research/sources.md's 130-row ledger. Revised the earlier standalone-vs-consolidated call after reading the actual consolidated statements: the company has no subsidiary for 9 of 10 years and acquired its one subsidiary mid-FY2023-24, so standalone throughout avoids a one-year comparability break. ebit/ebitda/net_working_capital are derived by a documented, cross-checked rule; financials.py gained real validation logic (to_numeric, check_ebit_identity); all 8 tests pass. | Day 3 - WACC module: cost of equity from Damodaran India ERP and beta (pages.stern.nyu.edu, now reachable), cost of debt from the filings, capital structure from the balance sheet already in data/GULFOILLUB/financials.csv |
| 2026-09-11 | `e0d7471` | Day 2 still blocked: confirmed via the egress proxy's own status log (not a blind retry) that the block is an organization policy denial (403), matching 09-09/09-10. No PDFs dropped in sources/raw/GULFOILLUB/ either. Used the day to close the one open modeling decision Day 2 left unresolved - prefer consolidated financials per fiscal year, falling back to standalone only where no consolidated statement exists - and tightened the resume note so a future run checks sources/raw/ first instead of re-diagnosing the same policy block a fourth time. No financials entered; no data fabricated. | Day 2 (retry) - once egress can reach india.gulfoilltd.com/investors/annual-reports (or an equivalent primary-source archive) or a human drops the ten annual-report PDFs into sources/raw/GULFOILLUB/, hand-enter Gulf Oil Lubricants India's ten years of consolidated financials (standalone only where no consolidated statement exists) into data/GULFOILLUB/financials.csv, citing every figure to document and page in research/sources.md's citation ledger |
| 2026-09-10 | `a0c78d6` | Day 2 re-blocked (confirmed, not transient): re-tested the same 5 finance hosts plus Google/Wikipedia/archive.org, all rejected the same way - this sandbox's egress is a categorical allowlist (only package-registry hosts reachable), not a finance-specific or flaky block. No financials fabricated. Instead scaffolded the Day 2 output: data/GULFOILLUB/financials.csv (10 fiscal-year rows x 14 line-item columns, every cell PENDING), reverse_dcf/financials.py (schema + pending-cell validator), and tests/test_financials_schema.py (5 tests, all passing) so real figures can drop in without a schema redesign. research/sources.md and README limitations updated with the sharper diagnosis and two concrete resume paths. | Day 2 (retry) - either (a) once the sandbox's network allowlist can reach india.gulfoilltd.com/investors/annual-reports or an equivalent primary-source archive, hand-enter the ten years of Gulf Oil Lubricants India financials into the now-scaffolded data/GULFOILLUB/financials.csv replacing PENDING cells, citing every figure to document and page in research/sources.md's citation ledger, or (b) if a human has dropped the source annual-report PDFs into sources/raw/GULFOILLUB/, transcribe from those local files instead |
| 2026-09-10 | `86fbf8f` | Day 2 blocked: sandbox network egress rejects every external host tried (Gulf Oil's own IR archive, screener.in, moneycontrol, NSE, BSE, Damodaran Online, FRED) via both curl and WebFetch - only WebSearch summaries are reachable, which cannot supply a real annual-report page citation. No financials were entered; fabricating page-cited numbers to fill the gap was rejected as dishonest. research/sources.md documents exactly what was tried and the resume plan; README limitations section updated to say the same. | Day 2 (retry) - once network egress can reach india.gulfoilltd.com/investors/annual-reports (or an equivalent primary-source filing archive), pull the FY2014-15 to FY2023-24 Gulf Oil Lubricants India annual reports and hand-enter ten years of financials into data/GULFOILLUB/financials.csv, every figure cited to document and page in research/sources.md |
| 2026-09-10 | `0b78eba` | Correction: Achintya reviewed the automated Day 1 pick (Kirloskar Ferrous, metals) and asked for a different sector plus stronger sourcing confidence for ten years of page-cited financials. Checked 5 more candidates against the same screen and swapped the pick to Gulf Oil Lubricants India (auto/industrial lubricants, thin coverage, dedicated IR annual-report archive covering FY2014-15 onward). Kirloskar Brothers is the fallback. Day 1's scope (shortlist + pick) is unchanged, only which company. | Day 2 - hand-enter ten years of Gulf Oil Lubricants India financials from annual reports into data/GULFOILLUB/financials.csv, every figure cited to a document and page in research/sources.md |
| 2026-09-09 | `f150767` | Day 1: screened NSE mid-caps against the project's cap/coverage/simplicity criteria using live market-cap and analyst-coverage data pulled today, shortlisted Kirloskar Ferrous Industries, Balaji Amines and Time Technoplast, and picked Kirloskar Ferrous (thinnest coverage, simplest single input-output business, genuinely cyclical history). No live user was available for the 'Achintya picks one' step, so the routine picked and recorded an explicit override/fallback order in research/shortlist.md. | Day 2 - hand-enter ten years of Kirloskar Ferrous financials from annual reports into data/KIRLFER/financials.csv, every figure cited to a document and page in research/sources.md |
<!-- CHECKPOINTS:END -->

## Where this sits

Part of a nine-repo research pipeline. Stock Stalker screens the NSE universe; this repo publishes a versioned artifact it reads back. This is the real shape as of Day 31 (P27) -- regenerated from `python -m reverse_dcf.solve --contract <path>` against the committed GULFOILLUB fixture, not a hand-written illustration (the pre-V2 example this replaced hadn't matched `to_contract()`'s actual output since v0.7, and its three populated keys are in fact `null` for today's real ticker and price):

```json
{
  "valuation": {
    "implied_cagr": null,
    "implied_ebit_margin": 0.133694140806081,
    "implied_reinvestment": null,
    "breakeven_growth": null,
    "implied_reinvestment_terminal": null,
    "median_roic": 0.25887134520602134,
    "terminal_roic": 0.11610477172909299,
    "price_reachable": false,
    "max_achievable_price_10y": 914.5482826509398,
    "growth_at_max_achievable_price_10y": 0.11609717839827303,
    "breakeven_reachable": false,
    "max_achievable_price_perpetual": 715.5156570453562,
    "growth_at_max_achievable_price_perpetual": 0.11609717839827302,
    "financials_source": "hand-entered, 10-year (GULFOILLUB base case)"
  }
}
```

The `null`s are V2/V3's honest answer for GULFOILLUB at its committed price (no constant growth rate reaches it -- see the v1/v2/v3 table above); `implied_ebit_margin`, `median_roic`, `terminal_roic` and the two `max_achievable_price*`/`growth_at_max_achievable_price*` ceiling pairs are always populated. Communication is by file contract, not imports, so either side can be refactored without breaking the other.

**Day 23 (C1): any-stock tear sheet, reverse DCF lite.** `base_case_from_financials`/`solve` were already ticker-agnostic in everything but their input -- GULFOILLUB's own ten-year, hand-transcribed `financials.csv`. `reverse_dcf/live_financials.py` is the yfinance adapter that fills that gap for any other ticker: 4-5 fiscal years from yfinance's own annual income statement, balance sheet and cash flow statement, mapped into the same `financials.py` schema (unit-converted to the schema's lakh convention, signed fields taken as an absolute magnitude, a documented fallback chain per field for issuers missing one row). Cross-checked against GULFOILLUB's own hand-entered data, not just internally consistent: FY2023-24 revenue from yfinance is within 0.3% of the hand-transcribed figure (`tests/test_live_financials.py`). Every contract this path produces carries `financials_source: "yfinance, consolidated, 4-5 years"` (an additive key; GULFOILLUB's own committed fixture has none, since its hand-entered ten-year base case needs no such flag) so nothing downstream mistakes a "lite" live result for the hand-verified one. `--live-financials` fetches the financials; `--prices-csv` reads the target price's latest close from an OHLCV CSV (e.g. STOCKSTALKER's own fixture for a ticker with no `reverse-dcf-engine` market fixture) instead of requiring one. Stock Stalker's front door (`stockstalker.live_contracts.generate_valuation_contract`) shells out to `python -m reverse_dcf.solve --live-financials` as a subprocess, the same pattern Day 21/22 already used for the risk/factor contracts, writing `outputs/contracts/<TICKER>/valuation.json` for a ticker with no committed `fixtures/valuation/<TICKER>.json`. Known simplification, recorded rather than hidden: `compute_wacc` still prices every ticker against Gulf Oil's own India "Chemical (Basic)" industry-beta fixture -- there is no free per-sector beta source wired up yet.

## Exam mapping

Series XV ch.10 (valuation principles, DCF), ch.12.6-12.7 (sensitivity, margin of safety)

---

CLI only, by design. No dashboard, no server. Charts and documents are written to `outputs/`.
