# Gulf Oil Lubricants India (NSE: GULFOILLUB) — what the price would require

*Reverse DCF, ₹1,039.00/share (screener.in, 2026-10-25). All figures reproducible with
`python -m reverse_dcf.solve`, `python -m reverse_dcf.compare`, `python -m reverse_dcf.sensitivity`,
`python -m reverse_dcf.grill`.*

## The sentence this project exists to produce

**At today's price, no constant revenue growth rate — positive, negative, or zero — reproduces
Gulf Oil Lubricants India's ₹1,039.00/share price under this model's growth/ROIC-consistent
reinvestment rule. The model's own ceiling is ₹904.98/share on the 10-year framing (reached at
+11.76% growth) and ₹708.41/share on the perpetual framing (also +11.76% growth) — today's price
sits ₹134.02 and ₹330.59 above each, respectively.**

That is a sharper version of this project's own contract-spec placeholder ("expectations exceed
history"): the price doesn't just sit above a growth rate this model finds unlikely, it sits
above the highest price this model can produce at all, anywhere in its feasible growth range,
at Gulf Oil's own historical capital efficiency.

## What the model implies

Holding Gulf Oil's FY2023-24 EBIT margin (13.37%) fixed, with reinvestment forced to scale with
growth at a ROIC that fades from the historical 9-year median (25.89%) to WACC (11.76% — CAPM,
Damodaran India industry beta relevered to Gulf Oil's own leverage, 7.06% risk-free rate) by the
terminal year, the reverse solver (`reverse_dcf/solve.py`) searches for the constant
explicit-period revenue growth rate that reproduces ₹1,039.00/share — and raises
`PriceUnreachableError` rather than returning a number pretending one exists:

| Framing | Result | Ceiling | Growth at ceiling |
|---|---|---|---|
| 10-year implied CAGR | **Unreachable** | **₹904.98/share** | +11.76% |
| Perpetual breakeven | **Unreachable** | **₹708.41/share** | +11.76% |

Both ceilings come straight from `solve()`'s own `max_achievable_price_10y`/`max_achievable_price_perpetual`
fields, not hand-derived: each is the highest price the forward DCF can produce anywhere in the
solver's feasible growth bracket, holding every other assumption at base case. Neither ceiling
moved when the committed price fixture refreshed from ₹1,061.00 (2026-09-12) to ₹1,066.00
(2026-10-19) and then ₹1,039.00 (2026-10-25) — the ceilings depend on margin, ROIC and WACC,
not on the target price itself. They did move when the WACC inputs refreshed on 2026-10-25
(risk-free rate 6.89% → 7.06%, WACC 11.61% → 11.76%): ₹914.55 → ₹904.98 (10-year) and
₹715.52 → ₹708.41 (perpetual).

## Whether it holds up

| Entity | Basis | 10-year revenue CAGR |
|---|---|---|
| Gulf Oil (implied, 10yr) | today's price | unreachable — ceiling ₹904.98/share, +11.76% growth |
| Gulf Oil (implied, perpetual breakeven) | today's price | unreachable — ceiling ₹708.41/share, +11.76% growth |
| Gulf Oil (realized) | own financials, FY2014-15→FY2023-24 | **14.54%** |
| Castrol India | screener.in, standalone | 6.0% |
| Savita Oil Technologies | screener.in, standalone | 11.0% |
| Gandhar Oil Refinery | screener.in, *consolidated* (standalone too short) | 9.0% |
| Gulf Oil (screener.in cross-check) | screener.in's own figure | 15.0% (close to 14.54% above; see limitations) |

No constant growth rate takes this model above either ceiling, so there is no single implied-CAGR
number to set against history or peers the way v1 and v2 did — the ceiling itself is the
comparison now. Even at the ceiling growth (+11.76%, where the terminal ROIC spread over WACC
hits zero and reinvestment absorbs the rest), the 10-year model stops ₹134.02 short of today's
price, and the perpetual model ₹330.59 short. Gulf Oil's own realized growth (14.54%) and every
peer checked (6.0%–11.0%, plus the 15.0% cross-check) sit in the table for context, but reading
this as "the market expects slower growth than history" (a statement about growth rates) would
understate it: the honest statement is "no growth rate this model can produce, at Gulf Oil's own
recent capital efficiency, reaches this price" (a statement about reachability).

### How much of this is the model, not the market

Shocking each of the model's five fixed assumptions one at a time (`python -m reverse_dcf.sensitivity`,
`outputs/tornado.png`) shows which, if any, can bring today's price into reach:

| Assumption | Base | Low shock → result | High shock → result |
|---|---|---|---|
| Reinvestment rate (mean of 9-yr history) | 25.24% | -26.02% → reachable, -1.83% growth | +76.49% → reachable, +20.00% growth |
| Terminal ROIC spread | 0.00% | -2.00% → unreachable | +2.00% → reachable, +11.02% growth |
| WACC | 11.76% | 10.76% → unreachable | 12.76% → unreachable |
| Terminal growth | 7.06% | 6.06% → unreachable | 8.06% → unreachable |
| EBIT margin | 13.37% | 11.07% → unreachable | 15.67% → reachable, +11.46% growth |

Three of the five shocks make today's price reachable. Until the 2026-10-25 refresh (price ₹1,066.00,
WACC 11.61%) the EBIT-margin high shock (15.67%) did not; at ₹1,039.00 and 11.76% it does, at
+11.46% growth. The other two require assuming something more generous than Gulf Oil's own
stated base case: a reinvestment rate far outside
its own historical range (+76.49%, beyond Gulf Oil's own highest realized year), or a terminal
ROIC spread above WACC held forever (+2pp) that this project does not assert as a base case
(PLAN.md rule 4). WACC and terminal growth, shocked at sizes grounded in standard DCF convention, leave the price
unreachable at both ends, and so does the EBIT-margin low shock.

Sweeping every one of Gulf Oil's own nine historically realized (margin, reinvestment) year-pairs
through the solver directly (`python -m reverse_dcf.solve --grid`), rather than shocking one
assumption at a time off the base case, finds implied growth ranging from about -5.3% to +25.3%
across those pairs — seven of the nine do produce a reachable number (only the two
highest-reinvestment years fall outside the solver's bracket, printed `n/a`). That range brackets
zero and reaches above Gulf Oil's own realized 14.54%, so the base-case ceiling above is not the
only lens on this data — see "Reading the finding" below.

### Reading the finding

Two things are both true and need to be read together, not collapsed into one. First: holding
every assumption at Gulf Oil's single most recent fiscal year (the base case above), today's
price is unreachable by a wide margin on both framings — not a soft "expectations undershoot
history" finding but a harder "the model's own ceiling, at this company's recent capital
efficiency, sits below the price" one. Second: letting margin and reinvestment vary across Gulf
Oil's own nine realized year-pairs (the grid), rather than freezing them at one year, produces a
range that does reach higher growth rates than the base case's own reinvestment-rate shock alone
would suggest, because several of Gulf Oil's historical years ran a materially higher
reinvestment rate than FY2023-24's. Which of these is the more honest statement about how this
price compares to Gulf Oil's history depends on which base year, if any, is representative of
Gulf Oil going forward — a judgement this single-company DCF cannot settle on its own; see
limitations.

### Day 9 — attacking the conclusion

Three checks against the modeling choices above, run mechanically (`python -m reverse_dcf.grill`)
rather than argued in prose:

1. **Is the 14.54% realized-history anchor itself propped up by a bad base year?** The README
   already flags FY2014-15 as "not a normal first year" — Gulf Oil was a shell company until a
   Scheme of Arrangement transferred the lubricants business in that fiscal year — and an
   unrepresentative base year could inflate the realized-CAGR side of this report's comparison.
   Recomputing with FY2014-15 dropped (base year FY2015-16 instead) gives **15.86%**, *higher*
   than the 14.54% figure used throughout this report, not lower. This attack does not survive.
2. **Is the unreachable conclusion an artifact of the forecast_years=10 convention?** Rerunning
   the solver's horizon from 5 to 15 years moves the model's own 10-year-style ceiling from
   ₹790.05/share (5y) to ₹1,019.40/share (15y) — a real, non-trivial swing — but every one of the
   five tested horizons (5/7/10/12/15y) still reports unreachable; even the most generous horizon
   tested (15y) leaves the ceiling ₹19.60 short of today's ₹1,039.00 price. This attack does not
   survive either.
3. **Is the unreachable conclusion an artifact of anchoring the ROIC fade on the full 9-year
   history rather than a more recent window?** Recomputing the 10-year ceiling at trailing
   3/4/5-year ROIC windows instead gives ₹874.95, ₹875.74 and ₹876.53/share respectively — all
   *lower* than the full-history ₹904.98 ceiling, since Gulf Oil's own realized ROIC has trended
   down (27.16% in FY2015-16 to 23.02% in FY2023-24). A more recent anchor makes the finding more
   robust, not less. This attack does not survive.

None of the three checks moved the headline conclusion; the second and third narrow the room for
"unreachable" to be an artifact of either convention. `tests/test_grill.py` pins all three
results so a future fiscal year or price update that changes them fails loudly rather than
silently.

## Limitations

- **The price is a single live snapshot.** ₹1,039.00/share (2026-10-25) is a small move from
  Day 1's ~₹1,140-1,180 shortlist-day note and from the ₹1,066.00 price this report's own
  numbers were last solved against. A different day's fetch moves the exact gap to each ceiling;
  the model's own ceilings themselves do not move with the price, so the *unreachable* verdict is
  far less sensitive to the day's fetch than v1's point-estimate framing was.
- **The base case is one fiscal year, not a steady state**, and the biggest lever on the
  reachable-vs-unreachable question other than the terminal ROIC spread: FY2023-24's 25.89%
  median-ROIC anchor and 13.37% EBIT margin are real, cited numbers, but they are a snapshot of
  one year's inputs. The reinvestment-rate and grid results above exist precisely because the
  single base-case ceiling is not the whole picture.
- **The terminal ROIC spread (default 0%, i.e. terminal ROIC = WACC) is a stated convention, not
  a company-specific estimate, and the unreachable verdict is sensitive to it.** Hand-probing the
  spread (reproducible via `roic_spread=` on any `reverse_dcf.solve` function, and pinned by
  `tests/test_sensitivity.py`): spread 0% → ceiling ₹904.98 (unreachable); spread 2% → reachable
  at 11.02% growth; spread 5% → reachable at 7.88% growth; spread 10% → reachable at 5.66%
  growth. A spread that large asserts Gulf Oil keeps a durable above-cost-of-capital return
  forever, which this project does not assert as a base case (PLAN.md rule 4) — but a reader who
  believes that claim would reach a different conclusion than "unreachable."
- **Implied growth and perpetual breakeven answer different questions on purpose** (10 years then
  terminal decay, vs. the same rate forever) and are not meant to converge; both ceilings belong
  in the finding.
- **The peer set is three recognizable comparables, not a systematic screen**, and one of the
  three (Gandhar) is consolidated where the other two and Gulf Oil itself are standalone — its
  standalone entity is too recently restructured for screener.in to compute a 10-year figure.
  Peer numbers are screener.in's own calculation, not this project's page-cited transcription the
  way Gulf Oil's own financials are (`research/sources.md`).
- **WACC uses book-value capital structure** (no book-equity column in the Day 2 schema) and a
  Hamada-relevered industry beta that assumes debt carries zero systematic risk — both bias WACC
  in the same direction (understating the debt weight, understating levered beta), so 11.76% is
  more likely too low than too high, which would make the ceilings above, if anything,
  understated.
- **Ten years of hand-entered financials is a small sample.** Every figure is cited to a document
  and page (`research/sources.md`), but it is still one company's decade.
- **This is one company, priced with one method.** It cannot distinguish the market repricing
  growth stocks generally, industrial lubricants specifically, or just this one balance sheet —
  only that this price exceeds what this model can produce at this company's own recent capital
  efficiency.

Full data-quality and methodology detail (FY2014-15's restructuring-year distortion, the
standalone-vs-consolidated call, the EBIT/EBITDA derivation rules, sourcing gaps, the v2/v3
terminal-value fix itself) is in [`README.md`](README.md)'s own limitations section rather than
repeated here.

## What would change this conclusion

A materially different price, a different base year or ROIC-anchor window, or a terminal ROIC
spread wider than the 0%-over-WACC convention used here could each move the exact ceiling. None
of the robustness checks above moves either ceiling above today's price. Among everything shocked
in this report, the only ways to make today's price reachable at all are a reinvestment rate far
outside Gulf Oil's own historical range, or a durable terminal ROIC spread this project does not
assert as a base case — neither is a change in the facts reported here, only in which assumption
a reader chooses to believe instead.

---

*Prepared as Day 8 of a bounded, day-by-day build; the Day 9 section above was added and attacked
on Day 9, and this report was regenerated on Day 90 against the v3 growth/ROIC-consistent
terminal model and the then-current committed price (CRITIQUES.md S5, P14 — v1's "-0.49% implied
CAGR" / "3.52% perpetual breakeven" framing and numbers, superseded by v2/v3's "unreachable"
finding since Day 4/18, had never been carried into this file until now). Methodology, data
sources, and the full checkpoint log are in [`README.md`](README.md). All figures above are
reproduced live by `python -m reverse_dcf.solve`, `python -m reverse_dcf.solve --grid`,
`python -m reverse_dcf.compare`, `python -m reverse_dcf.sensitivity`, and `python -m reverse_dcf.grill`
against the fixtures committed in this repo. Regenerated again on 26 Oct 2026 after the
2026-10-25 WACC and price refresh (hub CRITIQUES.md D30); `tests/test_report_numbers.py` now
fails if the headline ceilings, price or WACC here drift from `solve`'s output.*
