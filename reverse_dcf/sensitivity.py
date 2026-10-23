"""Sensitivity analysis and tornado chart (Day 7).

Day 5's solver holds WACC, EBIT margin, reinvestment rate, terminal growth
and the terminal ROIC spread fixed at Gulf Oil's own latest-fiscal-year
actuals (or a fixture default/stated convention) and finds the one number -
implied revenue growth - that reproduces today's price. That leaves an
obvious question unanswered: which of those five fixed assumptions does the
implied-growth number actually depend on? A reader who disagrees with the
WACC estimate needs to know whether that disagreement moves the headline
number by a rounding error or by several points.

This module answers it by shocking each assumption one at a time, holding
the other four at base case, and re-running :func:`reverse_dcf.solve.implied_growth`
at the shocked low and high value. The resulting range is plotted as a
tornado chart: variables sorted so the one that swings implied growth the
most sits at the top.

**Shock sizes are not invented.** For EBIT margin and reinvestment rate,
:func:`reverse_dcf.solve.historical_margins_and_reinvestment` already has
Gulf Oil's own nine-to-ten-year time series for both, so the shock is +/- one
population standard deviation of that history - the range Gulf Oil's own
operating profile has actually moved within, not an arbitrary +/-2pp. WACC
and terminal growth have no equivalent multi-year series in this repo (WACC
is a point-in-time CAPM estimate; terminal growth defaults to today's
risk-free rate), so those two use the standard textbook DCF-sensitivity
convention of a +/-1 percentage point shock instead. The terminal ROIC
spread has no historical series either (CRITIQUES.md V13: it is a stated
convention, not a company-specific estimate), so its shock instead mirrors
the one concrete threshold README.md already names by hand: +/-2 percentage
points, the point at which the real market price's "unreachable" headline
conclusion flips (see :data:`ROIC_SPREAD_SHOCK`). That asymmetry in method
is itself worth stating plainly rather than papering over with a uniform
shock size that would only look more rigorous.
"""

from __future__ import annotations

import argparse
import statistics
import textwrap
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from reverse_dcf.forward import DEFAULT_FINANCIALS, TERMINAL_ROIC_SPREAD_DEFAULT, base_case_from_financials
from reverse_dcf.solve import (
    GROWTH_BRACKET,
    MARKET_FIXTURES,
    PriceUnreachableError,
    historical_margins_and_reinvestment,
    implied_growth,
    load_market_price,
)

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "outputs"

WACC_SHOCK = 0.01
"""+/-1 percentage point - the standard textbook DCF-sensitivity convention,
used where no multi-year history exists to ground the shock in (see module
docstring)."""

TERMINAL_GROWTH_SHOCK = 0.01
"""Same convention and same reasoning as :data:`WACC_SHOCK`."""

ROIC_SPREAD_SHOCK = 0.02
"""+/-2 percentage points around :data:`reverse_dcf.forward.TERMINAL_ROIC_SPREAD_DEFAULT`
(0, i.e. terminal ROIC = WACC). CRITIQUES.md V13: README.md's own hand-probed
``roic_spread`` values single out +2pp as the modest, named threshold where
the headline "unreachable at the real price" conclusion flips to reachable --
not an arbitrary round number, and not this module's usual
historical-standard-deviation basis (``roic_spread`` has no historical
series of its own; it is a stated convention, not an estimate)."""


@dataclass(frozen=True)
class SensitivityRow:
    variable: str
    label: str
    base_value: float
    low_value: float
    high_value: float
    low_growth: float
    high_growth: float

    @property
    def swing(self) -> float:
        """Absolute range of implied growth this variable's shock produces - the tornado's sort key.

        ``NaN`` (never raised) when either end is unreachable under V2 --
        see :func:`sensitivity_table`. Python's ``sort`` tolerates NaN
        values (it just leaves their relative order among themselves
        undefined), so an unreachable row doesn't crash the sort, only
        ends up in an arbitrary position among other unreachable rows.
        """
        return abs(self.high_growth - self.low_growth)


def sensitivity_table(
    target_price: float,
    financials_path: str | Path = DEFAULT_FINANCIALS,
    *,
    forecast_years: int = 10,
    bracket: tuple[float, float] = GROWTH_BRACKET,
) -> list[SensitivityRow]:
    """Shock each of the five fixed DCF assumptions one at a time and re-solve implied growth.

    Returns rows sorted by :attr:`SensitivityRow.swing`, largest first - the
    order a tornado chart draws top to bottom.
    """
    base = base_case_from_financials(financials_path, revenue_growth=0.0, forecast_years=forecast_years)
    margins, reinvestment = historical_margins_and_reinvestment(financials_path)
    margin_shock = statistics.pstdev(margins.values())
    reinvestment_shock = statistics.pstdev(reinvestment.values())
    # V2 (CRITIQUES.md V1): base.reinvestment_rate is no longer a single
    # historical fiscal-year rate -- at revenue_growth=0.0 it is an all-zero
    # schedule (see base_case_from_financials), which isn't a meaningful
    # sensitivity-row midpoint. This row still asks the same question it
    # always did ("what if reinvestment deviated by +/-1 std from Gulf
    # Oil's own historical range, instead of following the growth/ROIC
    # model"), so its base_value is now the mean of that same historical
    # series instead.
    reinvestment_mean = statistics.mean(reinvestment.values())

    specs = [
        ("wacc", "WACC", base.wacc, WACC_SHOCK, "wacc"),
        ("terminal_growth", "Terminal growth", base.terminal_growth, TERMINAL_GROWTH_SHOCK, "terminal_growth"),
        ("ebit_margin", "EBIT margin", base.ebit_margin, margin_shock, "ebit_margin"),
        ("reinvestment_rate", "Reinvestment rate", reinvestment_mean, reinvestment_shock, "reinvestment_rate"),
        (
            "roic_spread",
            "Terminal ROIC spread",
            TERMINAL_ROIC_SPREAD_DEFAULT,
            ROIC_SPREAD_SHOCK,
            "roic_spread",
        ),
    ]

    def _implied_growth_or_nan(**override) -> float:
        # V2 (CRITIQUES.md V1): a shocked assumption can itself make the
        # target price unreachable (see reverse_dcf.forward.roic_fade_schedule
        # and reverse_dcf.solve._solve_growth) -- same NaN-for-no-root
        # convention reverse_dcf.solve.grid_implied_growth already uses for
        # its own margin x reinvestment grid, not a new idiom.
        try:
            return implied_growth(target_price, financials_path, forecast_years=forecast_years, bracket=bracket, **override)
        except PriceUnreachableError:
            return float("nan")

    rows = []
    for variable, label, base_value, shock, override_kw in specs:
        low_value = base_value - shock
        high_value = base_value + shock
        low_growth = _implied_growth_or_nan(**{override_kw: low_value})
        high_growth = _implied_growth_or_nan(**{override_kw: high_value})
        rows.append(SensitivityRow(variable, label, base_value, low_value, high_value, low_growth, high_growth))

    rows.sort(key=lambda r: (pd.isna(r.swing), -0.0 if pd.isna(r.swing) else -r.swing))
    return rows


def to_frame(rows: list[SensitivityRow]) -> pd.DataFrame:
    """Rows as a DataFrame, for the CLI table and for tests to check shape/content without touching matplotlib."""
    return pd.DataFrame(
        {
            "variable": [r.variable for r in rows],
            "base_value": [r.base_value for r in rows],
            "low_value": [r.low_value for r in rows],
            "high_value": [r.high_value for r in rows],
            "low_growth": [r.low_growth for r in rows],
            "high_growth": [r.high_growth for r in rows],
            "swing": [r.swing for r in rows],
        }
    )


UP_COLOR = "#2a78d6"
"""Blue - the shock direction (low/high input value) that raises implied growth."""
DOWN_COLOR = "#e34948"
"""Red - the shock direction that lowers implied growth. Blue<->red is this
portfolio's diverging pair (see the hub's dataviz reference): warm/cool poles
that read as opposite, used here for "raises the number" vs "lowers it"
rather than for a third, unrelated meaning."""
INK = "#0b0b0b"
MUTED = "#898781"
GRID = "#e1e0d9"


def plot_tornado(rows: list[SensitivityRow], ticker: str, target_price: float, output_path: str | Path) -> Path:
    """Render the tornado chart to ``output_path`` (a PNG) and return the path.

    Bars run from the lower to the higher of (low_growth, high_growth) for
    each variable - colored by which end is which, not by the bar's screen
    position - and are drawn in the order :func:`sensitivity_table` returns,
    largest swing at the top.

    V2 (CRITIQUES.md V1): ``low_growth``/``high_growth`` can be NaN (one end,
    or both) when that shocked assumption makes the target price
    unreachable (see :func:`sensitivity_table`) -- a row with one finite end
    draws a short marker at that end labelled "other end unreachable"
    rather than a bar with an undefined width; a row with both ends NaN
    draws no mark at all, just the "both ends unreachable" label, and is
    left out of the axis-range calculation either way.
    """
    fig, ax = plt.subplots(figsize=(9, 4.5), facecolor="#fcfcfb")
    ax.set_facecolor("#fcfcfb")

    labels = [r.label for r in rows]
    y_pos = range(len(rows))[::-1]  # largest swing at the top

    finite_values = [v for r in rows for v in (r.low_growth, r.high_growth) if pd.notna(v)]
    growth_lo = min(finite_values)
    growth_hi = max(finite_values)
    span = growth_hi - growth_lo
    pad = span * 0.22  # room for the value labels beyond each bar end
    ax.set_xlim(growth_lo - pad, growth_hi + pad)
    label_gap = span * 0.015

    for y, r in zip(y_pos, rows):
        low_finite, high_finite = pd.notna(r.low_growth), pd.notna(r.high_growth)
        if low_finite and high_finite:
            lo, hi = sorted((r.low_growth, r.high_growth))
            low_is_low_value = r.low_growth <= r.high_growth
            ax.barh(
                y,
                hi - lo,
                left=lo,
                height=0.55,
                color=UP_COLOR if low_is_low_value else DOWN_COLOR,
                edgecolor="#fcfcfb",
                linewidth=2,
            )
            ax.text(lo - label_gap, y, f"{r.low_value:.1%}", ha="right", va="center", fontsize=8, color=MUTED)
            ax.text(hi + label_gap, y, f"{r.high_value:.1%}", ha="left", va="center", fontsize=8, color=MUTED)
        elif low_finite or high_finite:
            finite_g = r.low_growth if low_finite else r.high_growth
            finite_value = r.low_value if low_finite else r.high_value
            ax.scatter([finite_g], [y], color=UP_COLOR, s=28, zorder=3)
            ax.text(
                finite_g + label_gap, y, f"{finite_value:.1%} (other end unreachable under V2)",
                ha="left", va="center", fontsize=8, color=MUTED,
            )
        else:
            ax.text(
                growth_lo, y, "unreachable at either shock value under V2",
                ha="left", va="center", fontsize=8, color=MUTED, style="italic",
            )

    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(labels, color=INK, fontsize=10)
    ax.set_xlabel("Implied 10-year revenue growth (CAGR)", color=INK, fontsize=9)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.tick_params(axis="x", colors=MUTED, labelsize=8)
    ax.grid(axis="x", color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(MUTED)

    subtitle = "\n".join(
        textwrap.wrap(
            "Label at each bar end is the assumption's own low/high value (not a legend) - "
            "blue raises implied growth, red lowers it.",
            width=70,
        )
    )
    ax.set_title(
        f"{ticker} implied growth sensitivity at Rs{target_price:,.0f}/share\n{subtitle}",
        color=INK,
        fontsize=10,
        loc="left",
    )
    fig.tight_layout()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="GULFOILLUB")
    parser.add_argument("--financials", default=str(DEFAULT_FINANCIALS))
    parser.add_argument("--price", type=float, default=None, help="current market price; defaults to fixtures/market/<ticker>.csv")
    parser.add_argument("--years", type=int, default=10, help="explicit forecast horizon in years")
    parser.add_argument("--output", default=str(OUTPUTS / "tornado.png"), help="path to write the tornado chart PNG")
    args = parser.parse_args()

    if args.price is None:
        price = load_market_price(args.ticker).price
    else:
        price = args.price

    rows = sensitivity_table(price, args.financials, forecast_years=args.years)

    print(f"Sensitivity of implied growth to each fixed assumption -- {args.ticker} at Rs{price:,.2f}/share\n")
    for r in rows:
        print(
            f"  {r.label:<21} base {r.base_value:>7.2%}  |  "
            f"{r.low_value:>7.2%} -> {r.low_growth:>+7.2%}   "
            f"{r.high_value:>7.2%} -> {r.high_growth:>+7.2%}   "
            f"swing {r.swing:>6.2%}"
        )

    path = plot_tornado(rows, args.ticker, price, args.output)
    print(f"\nTornado chart written to {path}")


if __name__ == "__main__":
    main()
