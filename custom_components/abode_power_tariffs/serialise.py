"""Rendering the plan as text, for diagnostics. Pure module.

Output only. There is no text import: with rates defined once, a period is
three fields, and a paste format would be a second way to enter the same thing
with every rate name an unvalidated string.
"""

from __future__ import annotations

import csv
import io

from .const import ALL_DAY_TOKENS
from .plan import DayPattern, Plan, format_time, qualified_name

PERIOD_HEADER = (
    "day_pattern",
    "days",
    "season_from",
    "season_to",
    "start",
    "end",
    "rate",
    "rate_id",
)
RATE_HEADER = (
    "rate",
    "timetable",
    "rate_id",
    "import_c_per_kwh",
    "constraints",
    "coasting_permitted",
    "rate_allowance_kwh",
    "fallback_rate",
)
EXPORT_RATE_HEADER = (
    "rate",
    "timetable",
    "rate_id",
    "export_c_per_kwh",
    "constraints",
    "coasting_permitted",
    "allowance_kwh",
    "fallback_c_per_kwh",
    "demand_period",
    "demand_rate_per_kw_month",
)


def _period_rate_id(day_pattern: DayPattern, name: str, plan_name: str) -> str:
    """Return the published identifier for the rate a period names.

    The bare name is what the user typed and is not unique across the plan: a
    weekday Peak and a weekend Peak are two rates both called Peak.
    """
    rate = day_pattern.rate_by_name(name)
    return "" if rate is None else qualified_name(plan_name, day_pattern.name, name)


def periods_to_csv(plan: Plan) -> str:
    """Render every period in the plan as CSV."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(PERIOD_HEADER)
    for day_pattern in plan.day_patterns:
        days = " ".join(token for token in ALL_DAY_TOKENS if token in day_pattern.days)
        season_from = (
            f"{day_pattern.season_from[0]:02d}-{day_pattern.season_from[1]:02d}"
            if day_pattern.season_from
            else ""
        )
        season_to = (
            f"{day_pattern.season_to[0]:02d}-{day_pattern.season_to[1]:02d}"
            if day_pattern.season_to
            else ""
        )
        for period in day_pattern.sorted_periods():
            writer.writerow(
                [
                    day_pattern.name,
                    days,
                    season_from,
                    season_to,
                    format_time(period.start),
                    format_time(period.end),
                    period.rate,
                    _period_rate_id(day_pattern, period.rate, plan.name),
                ]
            )
    return buffer.getvalue()


def rates_to_csv(plan: Plan) -> str:
    """Render every import rate in the plan as CSV."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(RATE_HEADER)
    for day_pattern, rate in plan.rates_with_pattern():
        writer.writerow(
            [
                rate.name,
                day_pattern.name,
                qualified_name(plan.name, day_pattern.name, rate.name),
                f"{rate.import_price * 100:.4f}",
                " ".join(sorted(rate.constraints)),
                "yes" if rate.coasting_permitted else "no",
                "" if rate.rate_allowance_kwh is None else rate.rate_allowance_kwh,
                rate.fallback_rate or "",
            ]
        )
    return buffer.getvalue()


def export_rates_to_csv(plan: Plan) -> str:
    """Render every export rate in the plan as CSV.

    The export equivalent of ``rates_to_csv`` (Gaps #2, #3, #4): an export
    rate now carries a demand declaration and a constraints declaration of
    its own, on top of the allowance and fallback it already had.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(EXPORT_RATE_HEADER)
    for day_pattern, rate in plan.export_rates_with_pattern():
        writer.writerow(
            [
                rate.name,
                day_pattern.name,
                qualified_name(plan.name, day_pattern.name, rate.name, export=True),
                f"{rate.price * 100:.4f}",
                " ".join(sorted(rate.constraints)),
                "yes" if rate.coasting_permitted else "no",
                "" if rate.allowance_kwh is None else rate.allowance_kwh,
                (
                    ""
                    if rate.fallback_price is None
                    else f"{rate.fallback_price * 100:.4f}"
                ),
                "yes" if rate.demand_period else "no",
                rate.demand_rate_per_kw_month,
            ]
        )
    return buffer.getvalue()
