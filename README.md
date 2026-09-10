# Reverse DCF engine

Takes a share price as given and solves for the growth, margin and reinvestment the market must already believe — then asks whether those assumptions are plausible.

**Status:** Last checkpoint 2026-09-10 · Next: Day 2 - hand-enter ten years of Gulf Oil Lubricants India financials from annual reports into data/GULFOILLUB/financials.csv, every figure cited to a document and page in research/sources.md

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
```

Runs offline against committed fixtures by default. Live data needs a key in `.env` (see `.env.example`); the fixture path is the default so nothing blocks on network access.

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

## Checkpoint log

<!-- CHECKPOINTS:START -->
| Date | Commit | What changed | Next |
|------|--------|--------------|------|
| 2026-09-10 | `0b78eba` | Correction: Achintya reviewed the automated Day 1 pick (Kirloskar Ferrous, metals) and asked for a different sector plus stronger sourcing confidence for ten years of page-cited financials. Checked 5 more candidates against the same screen and swapped the pick to Gulf Oil Lubricants India (auto/industrial lubricants, thin coverage, dedicated IR annual-report archive covering FY2014-15 onward). Kirloskar Brothers is the fallback. Day 1's scope (shortlist + pick) is unchanged, only which company. | Day 2 - hand-enter ten years of Gulf Oil Lubricants India financials from annual reports into data/GULFOILLUB/financials.csv, every figure cited to a document and page in research/sources.md |
| 2026-09-09 | `f150767` | Day 1: screened NSE mid-caps against the project's cap/coverage/simplicity criteria using live market-cap and analyst-coverage data pulled today, shortlisted Kirloskar Ferrous Industries, Balaji Amines and Time Technoplast, and picked Kirloskar Ferrous (thinnest coverage, simplest single input-output business, genuinely cyclical history). No live user was available for the 'Achintya picks one' step, so the routine picked and recorded an explicit override/fallback order in research/shortlist.md. | Day 2 - hand-enter ten years of Kirloskar Ferrous financials from annual reports into data/KIRLFER/financials.csv, every figure cited to a document and page in research/sources.md |
<!-- CHECKPOINTS:END -->

## Limitations and what would make me wrong

- Ten years of hand-entered financials is a small sample and a transcription risk. Every figure is cited so it can be checked.
- Implied assumptions are only as good as the WACC. The cost of equity uses a published India ERP rather than a bottom-up estimate.
- The solver assumes a single-stage-plus-terminal structure. A business mid-transition may not be well described by it.

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
