"""Forward FCFF DCF engine (Day 4).

Prices a company from an explicit set of assumptions, exactly the ordinary
direction: growth, margin and reinvestment go in, an implied share price
comes out. Day 5's reverse solver runs this engine inside a root-finder,
searching for the growth rate that makes the implied price equal today's
market price -- so every number this module needs must arrive as an
argument. There is nothing in here that hardcodes Gulf Oil, a fiscal year,
or a rate; :func:`base_case_from_financials` is the only place that reads
the committed data, and it does so by loading the latest fiscal year and
Day 3's WACC module, not by pasting numbers into the formulas.

Method, one line each:

- **Revenue** grows at a single constant rate for ``forecast_years``, then
  the terminal-value formula assumes the same constant-growth structure
  forever at (usually a slower) ``terminal_growth``. This is the
  single-stage-plus-terminal shape the README's limitations section already
  names -- a business mid-transition (a margin ramp, a reinvestment step
  change) is not well described by one constant growth rate.
- **FCFF** = EBIT x (1 - tax_rate) x (1 - reinvestment_rate). This is the
  standard reinvestment-rate formulation (Damodaran): reinvestment_rate is
  ``(capex - D&A + change in NWC) / NOPAT``, so the one rate absorbs capex,
  depreciation and working-capital movement instead of forecasting each
  separately -- see :func:`historical_reinvestment_rate` (the historical,
  one-fiscal-year read of it) and :func:`reinvestment_schedule_from_growth`
  (V2's default: a per-year rate re-derived from whatever growth is being
  forecast, via ``growth = reinvestment_rate x ROIC``, instead of one
  historical year's rate held fixed regardless of growth -- CRITIQUES.md V1).
- **Terminal value** is the Gordon growth formula on the first
  post-forecast FCFF, discounted back at the same WACC used for the
  explicit period. Requires ``wacc > terminal_growth``; that is not a
  numerical nicety, a perpetuity growing faster than its discount rate has
  no finite present value.
- **Equity value** = enterprise value - net debt (total debt - cash), at
  the same balance-sheet snapshot the WACC module used.
"""

from __future__ import annotations

import argparse
import statistics
from dataclasses import dataclass
from pathlib import Path

from reverse_dcf.financials import load_financials, to_numeric
from reverse_dcf.wacc import DEFAULT_FINANCIALS, compute_wacc, effective_tax_rate, load_risk_free_rate

LAKH_TO_RUPEES = 100_000
"""``data/GULFOILLUB/financials.csv`` reports every rupee figure in lakh (confirmed
against the README's ``96748.17`` FY2014-15 revenue = "₹967.5 cr"). ``shares_outstanding``
is a raw share count, not in lakh, so :func:`base_case_from_financials` converts every
rupee-denominated column to actual rupees before building :class:`DcfAssumptions` -
otherwise ``implied_share_price`` comes out in lakh-per-share, three orders of
magnitude too small."""


def project_revenue(revenue_base: float, growth_rate: float, years: int) -> list[float]:
    """Revenue for each of the next ``years`` years at a constant growth rate.

    Index 0 of the result is year 1 (``revenue_base`` grown once), not year 0.
    """
    if years < 1:
        raise ValueError("years must be at least 1")
    return [revenue_base * (1 + growth_rate) ** t for t in range(1, years + 1)]


def fcff_from_revenue(revenue: float, ebit_margin: float, tax_rate: float, reinvestment_rate: float) -> float:
    """FCFF = EBIT x (1 - tax) x (1 - reinvestment_rate) for one year's revenue."""
    ebit = revenue * ebit_margin
    nopat = ebit * (1 - tax_rate)
    return nopat * (1 - reinvestment_rate)


def project_fcff(
    revenues: list[float], ebit_margin: float, tax_rate: float, reinvestment_rate: float | list[float]
) -> list[float]:
    """FCFF for each year in ``revenues``, same margin/tax assumptions throughout.

    ``reinvestment_rate`` is either one rate applied to every year (the V1
    shape, still used by every override path in :mod:`reverse_dcf.solve` --
    the historical margin x reinvestment grid, the sensitivity tornado's flat
    shocks) or a list with one rate per year (V2's growth/ROIC-derived
    schedule, see :func:`reinvestment_schedule_from_growth`). Both shapes
    reach the same per-year formula; only how the rate is produced differs.
    """
    if isinstance(reinvestment_rate, (list, tuple)):
        if len(reinvestment_rate) != len(revenues):
            raise ValueError(
                f"reinvestment_rate has {len(reinvestment_rate)} entries but there are "
                f"{len(revenues)} forecast years"
            )
        rates = reinvestment_rate
    else:
        rates = [reinvestment_rate] * len(revenues)
    return [fcff_from_revenue(r, ebit_margin, tax_rate, rate) for r, rate in zip(revenues, rates)]


def present_value(cashflows: list[float], wacc: float) -> float:
    """Sum of ``cashflows`` discounted at ``wacc``, cashflows[0] received at t=1."""
    return sum(cf / (1 + wacc) ** t for t, cf in enumerate(cashflows, start=1))


def terminal_value(
    final_year_nopat: float, wacc: float, terminal_growth: float, terminal_reinvestment_rate: float
) -> float:
    """Gordon growth terminal value, as of the end of the explicit forecast (not discounted to today).

    V6 (CRITIQUES.md, Day 18): built from a *fresh* terminal year --
    ``final_year_nopat`` grown once more at ``terminal_growth`` and then
    reinvested at ``terminal_reinvestment_rate`` -- not by extrapolating the
    last explicit year's own FCFF forward at ``terminal_growth``, as this
    function did before Day 18. That extrapolation silently inherited
    whatever reinvestment rate funded the *explicit* growth rate (usually
    faster than ``terminal_growth``), breaking the ``growth =
    reinvestment_rate x ROIC`` identity exactly at the explicit/terminal
    boundary -- the mechanical reason V2's 10-year price fell once growth
    rose past ~1% even though GULFOILLUB's own ROIC exceeds WACC. Callers
    that want the pre-Day-18 "extrapolate the last year's own rate forever"
    behaviour pass that same rate as ``terminal_reinvestment_rate`` (see
    :func:`run_dcf`'s default when :attr:`DcfAssumptions.terminal_reinvestment_rate`
    is ``None``) -- the two are algebraically identical when the terminal
    rate equals the last explicit year's rate, so this is a strict
    generalisation, not a different formula for the cases that didn't have
    the bug.
    """
    if wacc <= terminal_growth:
        raise ValueError(
            f"wacc ({wacc:.4f}) must exceed terminal_growth ({terminal_growth:.4f}) "
            "for the terminal perpetuity to have a finite value"
        )
    next_year_nopat = final_year_nopat * (1 + terminal_growth)
    next_year_fcff = next_year_nopat * (1 - terminal_reinvestment_rate)
    return next_year_fcff / (wacc - terminal_growth)


def historical_reinvestment_rate(df_row: "pd.Series", prior_row: "pd.Series", tax_rate: float) -> float:
    """Reinvestment rate implied by one fiscal year's reported figures.

    ``(capex - D&A + change in net working capital) / NOPAT``. NOPAT is
    recomputed from ``ebit`` and ``tax_rate`` rather than taken from
    ``net_profit``, since NOPAT is unlevered (pre-interest) and net_profit
    is not.
    """
    nopat = df_row["ebit"] * (1 - tax_rate)
    change_in_nwc = df_row["net_working_capital"] - prior_row["net_working_capital"]
    reinvestment = df_row["capex"] - df_row["depreciation_amortization"] + change_in_nwc
    return reinvestment / nopat


def is_working_capital_release_year(df_row: "pd.Series", prior_row: "pd.Series") -> bool:
    """True when net working capital *fell* versus the prior fiscal year.

    A release year hands cash back into ``historical_reinvestment_rate``'s
    numerator instead of consuming it, which is how that rate goes negative
    even in years ``capex`` comfortably exceeds ``depreciation_amortization``
    (V1: the latest fiscal year, FY2023-24, is one of these). It is a
    one-off working-capital swing, not a sign that the business is
    shrinking its asset base, so a reinvestment rate built from a release
    year should not be read as "the company disinvests every year."
    """
    return df_row["net_working_capital"] < prior_row["net_working_capital"]


def invested_capital(df_row: "pd.Series") -> float:
    """Approximate invested capital for one fiscal year: ``total_assets - cash_and_equivalents``.

    ``financials.py``'s schema has no separate current-liabilities or
    book-equity column to net out non-interest-bearing current liabilities
    the textbook way (``invested capital = total debt + book equity -
    cash``), so this treats every non-cash asset as capital employed in the
    business. That overstates invested capital by whatever non-interest
    liabilities (trade payables, provisions) fund part of the asset base -
    a known approximation, not a precise book-equity figure, and good
    enough for :func:`historical_roic`'s job of bounding whether a
    reinvestment rate is economically plausible, not for a standalone ROIC
    headline.
    """
    return df_row["total_assets"] - df_row["cash_and_equivalents"]


def historical_roic(df_row: "pd.Series", prior_row: "pd.Series", tax_rate: float) -> float:
    """Return on invested capital for one fiscal year: NOPAT(t) / invested capital at the *start* of the year (t-1).

    Beginning-of-year capital, not the year-end figure, because the year's
    NOPAT was earned on the capital base already in place when the year
    started - the same convention :func:`reverse_dcf.wacc`'s cost of debt
    uses (averaging rather than year-end ``total_debt``) to avoid crediting
    a year's return to capital it only held for part of the year.
    """
    nopat = df_row["ebit"] * (1 - tax_rate)
    return nopat / invested_capital(prior_row)


def historical_roic_by_year(financials_path: str | Path = DEFAULT_FINANCIALS) -> dict[str, float]:
    """ROIC actually realized each fiscal year (years 2..N), from the committed financials.

    Moved here from :mod:`reverse_dcf.solve` (which still re-exports it by
    import, since ``tests/test_solve.py`` imports it from there) because V2's
    :func:`base_case_from_financials` now needs its median
    (:func:`historical_median_roic`) to build the base case, and this is the
    one place that already reads the financials CSV to call
    :func:`historical_roic` per year -- computing the same per-year series a
    second, independent way in two modules is exactly the kind of duplicated
    derivation that drifts the two apart.
    """
    df = to_numeric(load_financials(financials_path)).set_index("fiscal_year")
    years = list(df.index)
    tax_rates = {
        y: effective_tax_rate(df.loc[y, "ebit"], df.loc[y, "interest_expense"], df.loc[y, "tax_expense"])
        for y in years
    }
    return {y: historical_roic(df.loc[y], df.loc[py], tax_rates[y]) for py, y in zip(years, years[1:])}


MIN_ROIC_OBSERVATIONS = 3
"""V12 (CRITIQUES.md): the fewest year-over-year ROIC observations
:func:`historical_median_roic` will anchor the fade schedule on.
``live_financials.py``'s own :data:`live_financials.MIN_FISCAL_YEARS` (2)
lets the C1 "any ticker" path fetch as few as two fiscal years -- exactly
one year-over-year ROIC reading -- and a "median" of one point reports a
realized ROIC with full two-decimal confidence from a single year that
could be an outlier in either direction (a one-off margin spike, a
working-capital swing, a bad or unusually good year). Three observations
is still a thin anchor, but it is the smallest sample for which "median"
means anything other than "whichever one value happened to be reported" --
the same reasoning D15 already applied to the factor model's own minimum
sample floor. GULFOILLUB's real base case (10 fiscal years, 9 observations)
sits comfortably above it."""


def historical_median_roic(
    financials_path: str | Path = DEFAULT_FINANCIALS,
    *,
    ticker: str | None = None,
    trailing_years: int | None = None,
) -> float:
    """Median of :func:`historical_roic_by_year`'s per-fiscal-year series.

    V2's anchor for the *start* of the ROIC-fade schedule
    (:func:`roic_fade_schedule`): the business's own typical realized return
    on capital, not one single (possibly unusual) fiscal year -- the exact
    problem V1 had with reinvestment rate, now avoided for ROIC too.

    V12 (CRITIQUES.md): raises ``ValueError`` naming ``ticker`` (when given)
    and the observation count when fewer than :data:`MIN_ROIC_OBSERVATIONS`
    year-over-year ROIC readings are available, rather than silently
    anchoring the whole fade schedule on a single historical year.

    V14 (CRITIQUES.md): ``trailing_years``, when given, medians only the
    most recent ``trailing_years`` year-over-year observations
    (:func:`historical_roic_by_year` already returns them in fiscal-year
    order) instead of the full history -- the anchor-window robustness
    question :func:`reverse_dcf.grill.roic_anchor_robustness_check` exists
    to answer. A window wider than the available history is the same as
    no window at all; a window itself below :data:`MIN_ROIC_OBSERVATIONS`
    still raises, the same guard applying regardless of whether the
    thinness comes from the company's own short history or the caller's
    own windowing choice.
    """
    roic_by_year = historical_roic_by_year(financials_path)
    if trailing_years is not None:
        roic_by_year = dict(list(roic_by_year.items())[-trailing_years:])
    if len(roic_by_year) < MIN_ROIC_OBSERVATIONS:
        label = f"{ticker}: " if ticker else ""
        raise ValueError(
            f"{label}only {len(roic_by_year)} year-over-year ROIC observation(s) available "
            f"(need at least {MIN_ROIC_OBSERVATIONS} for historical_median_roic's anchor "
            "to mean more than a single year's reading)"
        )
    return statistics.median(roic_by_year.values())


TERMINAL_ROIC_SPREAD_DEFAULT = 0.0
"""V2's default spread of terminal-year ROIC over WACC: zero, not a company
read. The generic competitive-equilibrium assumption textbook corporate
finance uses for a terminal year (NISM XV ch.10/12's own convention): once
the explicit high-growth window ends, no firm earns an excess return over
its cost of capital forever, because competition erodes any advantage given
enough time. A nonzero spread would be a claim that this specific company
keeps a durable moat forever -- that is a view on the business, which this
routine does not write (PLAN.md rule 4: judgement stays with Achintya).
Callers may still override it, but the shipped default is not a prediction
about Gulf Oil."""


def terminal_roic(wacc: float, spread: float = TERMINAL_ROIC_SPREAD_DEFAULT) -> float:
    """ROIC assumed at the end of the explicit forecast: ``wacc + spread``. See :data:`TERMINAL_ROIC_SPREAD_DEFAULT`."""
    return wacc + spread


ROIC_NEAR_ZERO_EPSILON = 0.01
"""V8 (CRITIQUES.md): the smallest ROIC magnitude :func:`roic_fade_schedule`
accepts. The fundamental growth identity divides a forecast growth rate by
each year's ROIC (:func:`reinvestment_schedule_from_growth`); for GULFOILLUB's
own base case (median 25.89%, fading to a terminal 11.61%) that is always a
comfortably large divisor. ``live_financials.py``'s C1 "any ticker" path
derives this same linear fade from an arbitrary issuer's own historical ROIC,
with nothing stopping a loss-making or ROIC-volatile company's fade from
landing at or near zero -- the divisor then explodes into an astronomical
reinvestment rate (an injected -5% -> +10% fade over 10 years lands exactly
on 0.0 at year 4) instead of raising a clear, catchable error. 1 percentage
point is a plausibility floor, not a fit to any one company's numbers."""


def roic_fade_schedule(
    median_roic: float,
    terminal_roic_value: float,
    forecast_years: int,
    *,
    ticker: str | None = None,
) -> list[float]:
    """ROIC for each explicit forecast year, fading linearly from ``median_roic`` (year 1) to
    ``terminal_roic_value`` (the last explicit year).

    V1 held the whole ten-year reinvestment rate fixed at one historical
    fiscal year's actual. V2 instead lets the *efficiency* of that
    reinvestment (ROIC) decay over the explicit window from what the
    business has typically earned on capital toward the terminal
    assumption, while the growth rate itself stays the single constant
    ``revenue_growth`` the forward engine already models -- see
    :func:`reinvestment_schedule_from_growth` for how growth and this
    schedule combine into a reinvestment rate per year.

    ``forecast_years == 1`` has no fade length (a single year is both the
    first and the last), and that single year is exactly
    :func:`perpetual_breakeven_growth`'s "already in the terminal state"
    scenario, so it returns ``[terminal_roic_value]`` rather than
    ``[median_roic]``.

    V8 (CRITIQUES.md): raises ``ValueError`` naming ``ticker`` (when given)
    and the offending forecast year if any year in the fade falls within
    :data:`ROIC_NEAR_ZERO_EPSILON` of zero -- before any caller can divide a
    growth rate by it.
    """
    if forecast_years < 1:
        raise ValueError("forecast_years must be at least 1")
    if forecast_years == 1:
        schedule = [terminal_roic_value]
    else:
        step = (terminal_roic_value - median_roic) / (forecast_years - 1)
        schedule = [median_roic + step * t for t in range(forecast_years)]
    for year, roic in enumerate(schedule, start=1):
        if abs(roic) < ROIC_NEAR_ZERO_EPSILON:
            who = f"{ticker}: " if ticker else ""
            raise ValueError(
                f"{who}forecast year {year}'s ROIC ({roic:.2%}) is within "
                f"{ROIC_NEAR_ZERO_EPSILON:.2%} of zero in the median -> terminal "
                f"fade ({median_roic:.2%} -> {terminal_roic_value:.2%}) -- dividing "
                "a forecast growth rate by it would produce an astronomical "
                "reinvestment rate, not a real one"
            )
    return schedule


def reinvestment_schedule_from_growth(revenue_growth: float, roic_schedule: list[float]) -> list[float]:
    """Reinvestment rate per year: ``revenue_growth / roic`` for each year's ROIC in ``roic_schedule``.

    This *is* the fundamental growth identity
    (:func:`check_growth_reinvestment_consistency`'s ``growth = reinvestment_rate
    x ROIC``) solved for the reinvestment rate instead of asserted
    afterward -- so a schedule built this way satisfies that identity by
    construction, for every year, rather than needing to be checked against
    it. ``revenue_growth == 0`` always gives an all-zero schedule: a
    non-growing business needs no net new investment beyond maintenance
    capex, which the model already treats as embedded in depreciation.
    """
    return [revenue_growth / roic for roic in roic_schedule]


def check_growth_reinvestment_consistency(
    revenue_growth: float,
    reinvestment_rate: float,
    roic_band: tuple[float, float] = (0.0, 1.0),
) -> None:
    """Raise ``ValueError`` if ``revenue_growth`` and ``reinvestment_rate`` cannot come from the same real ROIC.

    The fundamental growth identity (Damodaran) is
    ``growth = reinvestment_rate x ROIC``. Two ways that identity breaks:

    - ``revenue_growth > 0`` with ``reinvestment_rate <= 0``: there is no
      real (let alone positive) ROIC that multiplies a non-positive
      reinvestment rate into positive growth. V1: Day 3-4 of
      ``NEXT_STEPS.md`` exists because :func:`base_case_from_financials`
      pairs a positive forecast growth rate with FY2023-24's
      reinvestment rate (-15.68%, a working-capital release year - see
      :func:`is_working_capital_release_year`) without ever checking this.
    - the ROIC the identity *would* imply (``revenue_growth /
      reinvestment_rate``, when the first check passes) falls outside
      ``roic_band``: a reinvestment rate close to zero makes the implied
      ROIC explode even for modest growth, which is a sign the reinvestment
      input is too small or noisy to drive a growth forecast, not a sign
      the company earns a 500% return on capital. The default band (0%,
      100%) is a plausibility bound on any real operating company's ROIC,
      not a Gulf-Oil-specific fit.
    """
    if revenue_growth > 0 and reinvestment_rate <= 0:
        raise ValueError(
            f"growth ({revenue_growth:.2%}) is positive but reinvestment_rate "
            f"({reinvestment_rate:.2%}) is not -- no real ROIC satisfies "
            "growth = reinvestment_rate x ROIC with a non-positive reinvestment rate"
        )
    if revenue_growth == 0:
        return
    implied_roic = revenue_growth / reinvestment_rate
    lo, hi = roic_band
    if not (lo <= implied_roic <= hi):
        raise ValueError(
            f"growth ({revenue_growth:.2%}) / reinvestment_rate ({reinvestment_rate:.2%}) "
            f"implies ROIC of {implied_roic:.2%}, outside the stated plausibility band "
            f"[{lo:.2%}, {hi:.2%}]"
        )


@dataclass(frozen=True)
class DcfAssumptions:
    revenue_base: float
    revenue_growth: float
    ebit_margin: float
    tax_rate: float
    reinvestment_rate: float | list[float]
    """A single rate for every forecast year (V1 and every override path), or
    one rate per year (V2's default -- see :func:`reinvestment_schedule_from_growth`)."""
    wacc: float
    terminal_growth: float
    forecast_years: int
    net_debt: float
    shares_outstanding: float
    terminal_reinvestment_rate: float | None = None
    """The rate reinvested in the single terminal year :func:`terminal_value`
    prices as a perpetuity (V6: CRITIQUES.md, Day 18) -- a *different*
    number from ``reinvestment_rate`` above whenever the explicit period's
    growth differs from ``terminal_growth``, since the explicit schedule is
    sized to fund the (usually faster) explicit growth rate, not the
    terminal one. ``None`` (every path before Day 18: both direct
    constructions, the CLI's ``--reinvestment-rate`` override, and
    :mod:`reverse_dcf.sensitivity`'s/``grid_implied_growth``'s flat-rate
    overrides) falls back in :func:`run_dcf` to the last explicit year's own
    rate -- i.e. the pre-Day-18 behaviour of extrapolating that year's FCFF
    forward unchanged, which is exactly right for a flat rate meant to hold
    forever. Only :func:`base_case_from_financials`'s V2 growth/ROIC
    schedule sets this explicitly, to ``terminal_growth / terminal_roic``."""


@dataclass(frozen=True)
class DcfResult:
    assumptions: DcfAssumptions
    revenues: list[float]
    fcffs: list[float]
    pv_explicit_fcff: float
    pv_terminal_value: float
    enterprise_value: float
    equity_value: float
    implied_share_price: float

    def summary(self) -> str:
        a = self.assumptions
        if isinstance(a.reinvestment_rate, (list, tuple)):
            reinvestment_line = (
                f"  Reinvestment rate (yr 1 -> yr {a.forecast_years}):     "
                f"{a.reinvestment_rate[0]:.2%} -> {a.reinvestment_rate[-1]:.2%}"
            )
        else:
            reinvestment_line = f"  Reinvestment rate:                  {a.reinvestment_rate:.2%}"
        lines = [
            f"Forward FCFF DCF -- {a.forecast_years}-year forecast",
            f"  Revenue growth (explicit period):   {a.revenue_growth:.2%}",
            f"  EBIT margin:                        {a.ebit_margin:.2%}",
            f"  Tax rate:                           {a.tax_rate:.2%}",
            reinvestment_line,
            f"  WACC:                               {a.wacc:.2%}",
            f"  Terminal growth:                    {a.terminal_growth:.2%}",
            f"  PV of explicit-period FCFF:          {self.pv_explicit_fcff:,.2f}",
            f"  PV of terminal value:                {self.pv_terminal_value:,.2f}",
            f"  Enterprise value:                    {self.enterprise_value:,.2f}",
            f"  Net debt:                            {a.net_debt:,.2f}",
            f"  Equity value:                        {self.equity_value:,.2f}",
            f"  Shares outstanding:                  {a.shares_outstanding:,.0f}",
            f"  Implied share price:                 {self.implied_share_price:,.2f}",
        ]
        return "\n".join(lines) + "\n"


def run_dcf(assumptions: DcfAssumptions) -> DcfResult:
    """Run the forward DCF end to end: assumptions in, an implied share price out."""
    revenues = project_revenue(assumptions.revenue_base, assumptions.revenue_growth, assumptions.forecast_years)
    fcffs = project_fcff(revenues, assumptions.ebit_margin, assumptions.tax_rate, assumptions.reinvestment_rate)

    pv_explicit = present_value(fcffs, assumptions.wacc)

    if assumptions.terminal_reinvestment_rate is not None:
        terminal_reinvestment_rate = assumptions.terminal_reinvestment_rate
    else:
        last_reinvestment_rate = assumptions.reinvestment_rate
        if isinstance(last_reinvestment_rate, (list, tuple)):
            last_reinvestment_rate = last_reinvestment_rate[-1]
        terminal_reinvestment_rate = last_reinvestment_rate
    final_year_nopat = revenues[-1] * assumptions.ebit_margin * (1 - assumptions.tax_rate)
    tv = terminal_value(final_year_nopat, assumptions.wacc, assumptions.terminal_growth, terminal_reinvestment_rate)
    pv_terminal = tv / (1 + assumptions.wacc) ** assumptions.forecast_years

    enterprise_value = pv_explicit + pv_terminal
    equity_value = enterprise_value - assumptions.net_debt
    implied_share_price = equity_value / assumptions.shares_outstanding

    return DcfResult(
        assumptions=assumptions,
        revenues=revenues,
        fcffs=fcffs,
        pv_explicit_fcff=pv_explicit,
        pv_terminal_value=pv_terminal,
        enterprise_value=enterprise_value,
        equity_value=equity_value,
        implied_share_price=implied_share_price,
    )


def base_case_from_financials(
    financials_path: str | Path = DEFAULT_FINANCIALS,
    *,
    revenue_growth: float,
    forecast_years: int = 10,
    terminal_growth: float | None = None,
    wacc: float | None = None,
    roic_spread: float = TERMINAL_ROIC_SPREAD_DEFAULT,
    ticker: str | None = None,
) -> DcfAssumptions:
    """Build a :class:`DcfAssumptions` off the latest fiscal year's actuals and Day 3's WACC.

    Only ``revenue_growth`` has no sensible default -- it is the number
    Day 5's solver exists to find, so this function refuses to guess one.
    EBIT margin and tax rate are read from the latest fiscal year in
    ``financials_path``; WACC from :func:`reverse_dcf.wacc.compute_wacc`
    unless ``wacc`` overrides it; terminal growth defaults to the same
    risk-free rate WACC uses, on Damodaran's own convention that a perpetual
    growth rate should not exceed the economy's long-run (proxied by the
    risk-free) growth rate.

    V2 (CRITIQUES.md V1): ``reinvestment_rate`` is no longer one historical
    fiscal year's actual rate held fixed regardless of the growth being
    forecast (V1's bug -- see
    :func:`check_growth_reinvestment_consistency`). It is now derived from
    ``revenue_growth`` itself via the fundamental growth identity, using a
    ROIC that fades from the business's own historical median
    (:func:`historical_median_roic`) toward ``wacc + roic_spread`` by the
    last explicit forecast year (:func:`roic_fade_schedule`,
    :func:`reinvestment_schedule_from_growth`) -- consistent by
    construction for any ``revenue_growth``, including 0 (an all-zero
    schedule: no net new investment needed without growth). ``wacc`` is a
    first-class parameter (not just a post-hoc ``dataclasses.replace``)
    specifically so that overriding it also moves this schedule's terminal
    anchor consistently, the way :mod:`reverse_dcf.sensitivity`'s WACC shock
    needs it to.

    ``ticker`` is passed through to :func:`roic_fade_schedule` (V8),
    :func:`reverse_dcf.wacc.effective_tax_rate` and
    :func:`reverse_dcf.wacc.compute_wacc` (V10/V11) only so a degenerate-input
    failure names the company it came from; it has no other effect here, and
    ``None`` (every call site before Day 29) keeps the error generic.
    """
    df = to_numeric(load_financials(financials_path)).set_index("fiscal_year")
    years = list(df.index)
    if len(years) < 2:
        raise ValueError("need at least two fiscal years to derive a reinvestment rate")
    current = df.loc[years[-1]]

    tax_rate = effective_tax_rate(
        current["ebit"], current["interest_expense"], current["tax_expense"], ticker=ticker
    )
    ebit_margin = current["ebit"] / current["revenue"]

    wacc_result = compute_wacc(financials_path, fiscal_year=years[-1], ticker=ticker)
    effective_wacc = wacc_result.wacc if wacc is None else wacc
    risk_free_rate = load_risk_free_rate()
    if terminal_growth is None:
        terminal_growth = risk_free_rate
    else:
        # V6 (CRITIQUES.md, Day 18): g-infinity -- the growth rate the
        # terminal year's own reinvestment is sized to sustain forever --
        # never exceeds the risk-free rate, same Damodaran convention this
        # function's docstring already states for the unoverridden default.
        # A caller passing a higher terminal_growth (e.g. the sensitivity
        # tornado's +1pp shock) gets the capped value consistently in both
        # the Gordon-growth discounting below and the terminal reinvestment
        # rate, not a growth rate paired with a reinvestment rate sized for
        # a different, uncapped number.
        terminal_growth = min(terminal_growth, risk_free_rate)

    median_roic = historical_median_roic(financials_path, ticker=ticker)
    terminal_roic_value = terminal_roic(effective_wacc, roic_spread)
    roic_schedule = roic_fade_schedule(median_roic, terminal_roic_value, forecast_years, ticker=ticker)
    reinvestment_rate = reinvestment_schedule_from_growth(revenue_growth, roic_schedule)
    # V6: the explicit schedule above is sized to fund revenue_growth, not
    # terminal_growth -- its last entry is *not* a valid terminal-year
    # reinvestment rate whenever the two differ (CRITIQUES.md V6). The
    # terminal year gets its own rate, satisfying the same growth =
    # reinvestment_rate x ROIC identity at terminal_growth and terminal_roic
    # instead.
    terminal_reinvestment_rate = terminal_growth / terminal_roic_value

    net_debt_lakh = current["total_debt"] - current["cash_and_equivalents"]
    return DcfAssumptions(
        revenue_base=current["revenue"] * LAKH_TO_RUPEES,
        revenue_growth=revenue_growth,
        ebit_margin=ebit_margin,
        tax_rate=tax_rate,
        reinvestment_rate=reinvestment_rate,
        wacc=effective_wacc,
        terminal_growth=terminal_growth,
        forecast_years=forecast_years,
        net_debt=net_debt_lakh * LAKH_TO_RUPEES,
        shares_outstanding=current["shares_outstanding"],
        terminal_reinvestment_rate=terminal_reinvestment_rate,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--financials", default=str(DEFAULT_FINANCIALS))
    parser.add_argument("--growth", type=float, required=True, help="explicit-period revenue growth, e.g. 0.10")
    parser.add_argument("--years", type=int, default=10, help="explicit forecast horizon in years")
    parser.add_argument(
        "--terminal-growth",
        type=float,
        default=None,
        help="defaults to the current India risk-free rate (fixtures/wacc/india_10y_gsec_yield.csv)",
    )
    parser.add_argument(
        "--margin",
        type=float,
        default=None,
        help="EBIT margin override; defaults to the latest fiscal year's actual margin",
    )
    parser.add_argument(
        "--reinvestment-rate",
        type=float,
        default=None,
        help="flat reinvestment rate override, applied to every forecast year; "
        "defaults to V2's growth/ROIC-derived per-year schedule (see base_case_from_financials)",
    )
    args = parser.parse_args()

    assumptions = base_case_from_financials(
        args.financials,
        revenue_growth=args.growth,
        forecast_years=args.years,
        terminal_growth=args.terminal_growth,
    )
    if args.margin is not None:
        assumptions = DcfAssumptions(**{**assumptions.__dict__, "ebit_margin": args.margin})
    if args.reinvestment_rate is not None:
        # A flat override is meant to hold forever (V1-style), so the
        # terminal year reinvests at that same flat rate too, not the V2
        # schedule's terminal_growth/terminal_roic figure computed above for
        # the unoverridden schedule -- see DcfAssumptions.terminal_reinvestment_rate.
        assumptions = DcfAssumptions(
            **{
                **assumptions.__dict__,
                "reinvestment_rate": args.reinvestment_rate,
                "terminal_reinvestment_rate": None,
            }
        )

    result = run_dcf(assumptions)
    print(result.summary())
    print(f"(Enterprise/equity value in rupees; ₹{result.enterprise_value / 1e7:,.1f} cr enterprise value)")


if __name__ == "__main__":
    main()
