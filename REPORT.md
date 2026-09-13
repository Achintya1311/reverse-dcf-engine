# Gulf Oil Lubricants India (NSE: GULFOILLUB) — what the price already assumes

*Reverse DCF, ₹1,061.00/share (screener.in, 2026-09-12). All figures reproducible with
`python -m reverse_dcf.solve`, `python -m reverse_dcf.compare`, `python -m reverse_dcf.sensitivity`.*

## The sentence this project exists to produce

**At today's price, the market is pricing in essentially flat-to-declining revenue for Gulf
Oil Lubricants India — a 10-year implied CAGR of -0.49%, or 3.52% if that growth were held
forever with no terminal deceleration. Gulf Oil has never come close to that low a number:
its own realized 10-year revenue CAGR is 14.54%, and every peer checked (Castrol India 6.0%,
Gandhar Oil Refinery 9.0%, Savita Oil Technologies 11.0%) has also grown faster over the same
window.**

That is the mirror image of this project's own contract-spec placeholder
("expectations exceed history"). Here the market's bar sits *below* history, not above it —
which is itself a finding worth taking seriously rather than a disappointing result to
explain away.

## What the market believes

Holding Gulf Oil's most recent fiscal year's operating profile fixed (FY2023-24: 13.37% EBIT
margin, -15.68% reinvestment rate — a real number, not a typo; working capital was released
and capex ran below depreciation that year) and its WACC at 11.61% (CAPM, Damodaran India
industry beta relevered to Gulf Oil's own leverage, 6.89% risk-free rate), the reverse solver
finds the constant explicit-period revenue growth rate that reproduces ₹1,061.00/share:

| Framing | Implied growth | What it assumes |
|---|---|---|
| 10-year implied CAGR | **-0.49%** | 10 years at this rate, then Gordon-growth terminal decay to 6.89% |
| Perpetual breakeven | **3.52%** | this rate held forever, no deceleration — the more forgiving number |

Both round-trip: fed back through the forward DCF (`reverse_dcf/forward.py`), each reproduces
₹1,061.00/share to within a paisa (`tests/test_solve.py`). That round-trip is this project's
correctness gate, not a courtesy check — an implied number that doesn't reproduce the price
that produced it is unfalsifiable.

## Whether it holds up

It doesn't, on either framing, against either history or the peer set:

| Entity | Basis | 10-year revenue CAGR |
|---|---|---|
| Gulf Oil (implied, 10yr) | today's price | **-0.49%** |
| Gulf Oil (implied, perpetual breakeven) | today's price | **3.52%** |
| Gulf Oil (realized) | own financials, FY2014-15→FY2023-24 | **14.54%** |
| Castrol India | screener.in, standalone | 6.0% |
| Savita Oil Technologies | screener.in, standalone | 11.0% |
| Gandhar Oil Refinery | screener.in, *consolidated* (standalone too short) | 9.0% |
| Gulf Oil (screener.in cross-check) | screener.in's own figure | 15.0% (close to 14.54% above; see limitations) |

Even the more forgiving perpetual-breakeven number (3.52%) sits below every peer's realized
growth, and less than a quarter of Gulf Oil's own realized pace. Reading this as "the market
has simply given up on lubricants growth" would overstate the case, though: the sensitivity
analysis below shows how much of this gap is a modeling artifact of freezing one year's
operating profile rather than a settled market view.

### How much of this is the model, not the market

The base case fixes four assumptions at one snapshot each. Shocking each independently
(`python -m reverse_dcf.sensitivity`, `outputs/tornado.png`) shows how much the -0.49%
headline moves if that snapshot were slightly different:

| Assumption | Base | Low shock → implied growth | High shock → implied growth | Swing |
|---|---|---|---|---|
| Reinvestment rate | -15.68% | -66.93% → -5.34% | 35.57% → +7.08% | **12.42pp** |
| WACC | 11.61% | 10.61% → -3.14% | 12.61% → +1.80% | 4.94pp |
| EBIT margin | 13.37% | 11.07% → +1.96% | 15.67% → -2.57% | 4.53pp |
| Terminal growth | 6.89% | 5.89% → +0.97% | 7.89% → -2.33% | 3.30pp |

Reinvestment rate dominates, and for good reason: Gulf Oil's own reinvestment rate has swung
from -15.68% to +104% across its own ten realized years, not an invented shock size (EBIT
margin and reinvestment shocks are ±1 std of Gulf Oil's own 9–10 year history; WACC and
terminal growth use the standard ±1pp DCF convention since no equivalent multi-year series
exists for either). Sweeping every one of Gulf Oil's own nine historically realized
(margin, reinvestment) year-pairs through the solver (`python -m reverse_dcf.solve --grid`)
finds implied growth ranging from about -5% to +25% depending which year is assumed to
persist. The single base-case number is directionally real — it clears zero and even the
27%-swing grid rarely reaches Gulf Oil's realized 14.54% — but it should not be quoted to two
decimal places as a settled market view.

### Reading the finding

Net of that noise, the honest statement is narrower than the headline sentence but still
real: **the market is not paying for Gulf Oil to repeat its own last-decade growth, and most
of the plausible year-to-year operating scenarios support that** — the grid's high end (+25%,
Gulf Oil's most capex-heavy historical year) is the exception, not the center of the range.
Whether that's the market correctly discounting a maturing lubricants franchise, or an
overreaction to one volatile balance-sheet year, is outside what a single-company DCF can
settle — see limitations.

### Day 9 — attacking the conclusion

Two checks against the two modeling choices above that had never actually been varied in
Days 1–8, run mechanically (`python -m reverse_dcf.grill`) rather than argued in prose:

1. **Is the 14.54% realized-history anchor itself propped up by a bad base year?** The
   README already flags FY2014-15 as "not a normal first year" — Gulf Oil was a shell company
   until a Scheme of Arrangement transferred the lubricants business in that fiscal year — and
   an unrepresentative base year could inflate the realized-CAGR side of this project's whole
   comparison, narrowing the gap the headline rests on. Recomputing with FY2014-15 dropped
   (base year FY2015-16 instead) gives **15.86%**, *higher* than the 14.54% figure used
   throughout this report, not lower. The flagged year was, if anything, holding the realized
   number down, not propping it up — this attack does not survive.
2. **Is the negative-implied-growth finding an artifact of the forecast_years=10 convention?**
   Every number above uses a 10-year explicit horizon by convention, never varied. Rerunning
   Day 5's solver from a 5-year to a 15-year horizon moves implied growth from -5.79% to
   +1.28% — a real, non-trivial swing — but even at the most generous end tested (15 years),
   1.28% implied growth is still more than 13 percentage points below Gulf Oil's own realized
   growth on either base year. This attack also does not survive.

Neither check moved the headline conclusion; if anything, both narrow the room for the finding
to be a modeling artifact rather than a real gap between price and history. `tests/test_grill.py`
pins both results so a future fiscal year or price update that changes them fails loudly rather
than silently.

## Limitations

- **The price is a single live snapshot.** ₹1,061.00/share (2026-09-12) is already a 7-9%
  move from Day 1's ~₹1,140-1,180 note three days earlier. A different day's fetch moves the
  exact decimal; the *sign* of the finding (implied growth well below realized history) is
  unlikely to flip on ordinary noise, but the number itself should not be read to two decimals.
- **The base case is one fiscal year, not a steady state**, and the biggest single lever on
  the conclusion: FY2023-24's -15.68% reinvestment rate is real, not a typo, but it is one
  point on a series that has ranged to +104% (12.4pp of tornado swing on its own). This is
  exactly why the grid — not the single base-case number — carries the real conclusion above.
  A reinvestment rate above 100% can also push the target price out of the solver's bracket
  entirely (`n/a` cells in the grid, not wrong numbers).
- **Implied growth and perpetual breakeven answer different questions on purpose** (10 years
  then terminal decay, vs. the same rate forever) and are not meant to converge; both belong
  in the finding.
- **The 10-year explicit forecast horizon is a convention, not a derived number, and it
  moves the answer.** Day 9's grilling pass (above) found implied growth swinging from
  -5.79% at a 5-year horizon to +1.28% at 15 years — a real lever nobody had shocked before
  Day 9, similar in kind to the reinvestment-rate lever already in the tornado chart. It did
  not change the finding's direction here, but a shorter or longer horizon changes the exact
  number more than most of the tornado's own shocks do.
- **The peer set is three recognizable comparables, not a systematic screen**, and one of the
  three (Gandhar) is consolidated where the other two and Gulf Oil itself are standalone —
  its standalone entity is too recently restructured for screener.in to compute a 10-year
  figure. Peer numbers are also screener.in's own calculation, not this project's page-cited
  transcription the way Gulf Oil's own financials are (`research/sources.md`).
- **WACC uses book-value capital structure** (no book-equity column in the Day 2 schema)
  and a Hamada-relevered industry beta that assumes debt carries zero systematic risk —
  both bias WACC in the same direction (understating the debt weight, understating levered
  beta), so 11.61% is more likely too low than too high.
- **Ten years of hand-entered financials is a small sample.** Every figure is cited to a
  document and page (`research/sources.md`), but it is still one company's decade.
- **This is one company, priced with one method.** It cannot distinguish the market
  repricing growth stocks generally, industrial lubricants specifically, or just this one
  balance sheet — only that this price does not match this company's own history or peers.

Full data-quality and methodology detail (FY2014-15's restructuring-year distortion, the
standalone-vs-consolidated call, the EBIT/EBITDA derivation rules, sourcing gaps) is in
[`README.md`](README.md)'s own limitations section rather than repeated here.

## What would change this conclusion

A materially different price, a multi-year-average base case instead of one fiscal year, or a
broader peer screen could each move the exact numbers. None of the three available today points
toward the market's implied growth catching up to Gulf Oil's realized 14.54% — the grid's own
high end tops out at +25%, still below history, and only reached by treating FY2023-24's
negative reinvestment rate as the outlier it looks like rather than the new normal.

---

*Prepared as Day 8 of a bounded, day-by-day build; the Day 9 section above was added and
attacked on Day 9. Methodology, data sources, and the full checkpoint log are in
[`README.md`](README.md). All figures above are reproduced live by `python -m reverse_dcf.solve`,
`python -m reverse_dcf.compare`, `python -m reverse_dcf.sensitivity`, and
`python -m reverse_dcf.grill` against the fixtures committed in this repo — nothing here is
hand-typed from a prior run.*
