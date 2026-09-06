# Reverse DCF engine

Takes a share price as given and solves for the growth, margin and reinvestment the market must already believe — then asks whether those assumptions are plausible.

**Status:** Not started · Next: Day 1 - shortlist 3 NSE mid-caps with written screening rationale

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

Nothing yet. This section fills in as the work lands, including the results that do not flatter the method.

## Checkpoint log

<!-- CHECKPOINTS:START -->
| Date | Commit | What changed | Next |
|------|--------|--------------|------|
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
