"""Rendering the plan as text. Pure module.

There used to be a coloured 24-hour bar here, drawn with emoji squares under a
character ruler. It could not be made to line up: the ruler is plain characters
and the squares are emoji, and their widths differ by font and platform, so the
bar drifted against the clock by hours on some browsers. A visual you cannot
read against the clock is worse than none.

So this renders the plan as plain text, which is exact everywhere, and the
picture is left to Home Assistant. `sensor.<n>_rate` is an enum, so a
built-in history-graph card draws it as a coloured timeline with a real time
axis. See the README.

One table. There used to be a second block underneath restating every rate and
its price with no times against them, which meant every price appeared twice
and the same rate was called two different things in the two places. The
identifier the second block existed to show is now a column of the first.
"""

from __future__ import annotations

from .plan import DayPattern, ExportRate, Plan, Rate, format_time, qualified_name
from .validate import validate_periods

# "00:00-24:00".
TIME_COLUMN = 11

MISSING = "rate missing"


def column_widths(plan: Plan) -> tuple[int, int]:
    """Return the name and identifier column widths for the whole plan.

    Measured once across every timetable, so two tables line up with each other
    and not merely each with itself. A fixed pad silently fails the moment a
    name outgrows it: the price is pushed right and the column bends round it.
    """
    names = 0
    identifiers = 0
    for day_pattern in plan.day_patterns:
        for period in (*day_pattern.periods, *day_pattern.export_periods):
            names = max(names, len(period.rate))
    for day_pattern, rate in plan.rates_with_pattern():
        names = max(names, len(rate.name))
        identifiers = max(
            identifiers, len(qualified_name(plan.name, day_pattern.name, rate.name))
        )
    for day_pattern, export_rate in plan.export_rates_with_pattern():
        names = max(names, len(export_rate.name))
        identifiers = max(
            identifiers,
            len(
                qualified_name(
                    plan.name, day_pattern.name, export_rate.name, export=True
                )
            ),
        )
    return names, identifiers


def name_width(plan: Plan) -> int:
    """Return the name column width on its own."""
    return column_widths(plan)[0]


def _row(
    time_cell: str,
    name: str,
    identifier: str,
    price: str,
    widths: tuple[int, int],
    indent: str = "  ",
) -> str:
    """Return one padded row of the table."""
    names, identifiers = widths
    return (
        f"{indent}{time_cell:<{TIME_COLUMN}}  {name:<{names}}  "
        f"{identifier:<{identifiers}}  {price}"
    ).rstrip()


def _price(cents: float) -> str:
    """Return a price cell, right-aligned on the decimal point."""
    return f"{cents:>7.2f} c/kWh"


def _rate_note(rate: Rate | ExportRate) -> str:
    """Return a one-line summary of what a rate declares beyond its price.

    Neither the plan preview nor the rate plan card showed a demand charge
    or an allowance anywhere — a rate could have one saved correctly and
    there was no way to see it without opening the rate again to check.
    """
    parts: list[str] = []
    if rate.has_demand_charge:
        basis = "day" if rate.demand_basis == "day" else "month"
        interval = (
            f"{rate.demand_interval} min interval"
            if rate.demand_interval
            else "instantaneous"
        )
        parts.append(
            f"demand: ${rate.demand_rate_per_kw_month:.2f}/kW/{basis}, {interval}"
        )
    if rate.has_allowance:
        cap = rate.rate_allowance_kwh if isinstance(rate, Rate) else rate.allowance_kwh
        assert cap is not None
        if isinstance(rate, Rate):
            period = "per cycle" if rate.counts_monthly_allowance else "per slot"
            fallback = rate.fallback_rate or "nothing declared"
        else:
            period = "per slot"
            fallback = (
                f"{rate.fallback_price:.4f}/kWh"
                if rate.fallback_price is not None
                else "nothing declared"
            )
        parts.append(f"allowance: {cap:g} kWh {period}, then {fallback}")
    return "  ·  ".join(parts)


def render_export_row(
    plan: Plan, day_pattern: DayPattern, widths: tuple[int, int] | None = None
) -> str:
    """Return the feed-in side of one timetable, in the same columns."""
    columns = column_widths(plan) if widths is None else widths
    if day_pattern.export_same_all_day:
        return f"  Feed-in: {day_pattern.export_flat_price * 100:.2f} c/kWh all day"

    lines = ["  Feed-in:"]
    for period in day_pattern.sorted_export_periods():
        rate = day_pattern.export_rate_by_name(period.rate)
        identifier = (
            ""
            if rate is None
            else qualified_name(plan.name, day_pattern.name, rate.name, export=True)
        )
        lines.append(
            _row(
                f"{format_time(period.start)}-{format_time(period.end)}",
                period.rate,
                identifier,
                MISSING if rate is None else _price(rate.price * 100),
                columns,
                indent="    ",
            )
        )
        if rate is not None:
            note = _rate_note(rate)
            if note:
                lines.append(f"      {note}")
    return "\n".join(lines)


def render_day_pattern(
    plan: Plan, day_pattern: DayPattern, widths: tuple[int, int] | None = None
) -> str:
    """Render one timetable as a table: when, what it is called, its id, its price."""
    columns = column_widths(plan) if widths is None else widths
    season = ""
    if day_pattern.is_seasonal:
        assert day_pattern.season_from is not None
        assert day_pattern.season_to is not None
        season = (
            f"  ({day_pattern.season_from[1]:02d}/{day_pattern.season_from[0]:02d}"
            f" - {day_pattern.season_to[1]:02d}/{day_pattern.season_to[0]:02d})"
        )

    lines = [f"{day_pattern.name}{season}"]
    for period in day_pattern.sorted_periods():
        rate = day_pattern.rate_by_name(period.rate)
        identifier = (
            ""
            if rate is None
            else qualified_name(plan.name, day_pattern.name, rate.name)
        )
        lines.append(
            _row(
                f"{format_time(period.start)}-{format_time(period.end)}",
                period.rate,
                identifier,
                MISSING if rate is None else _price(rate.import_price * 100),
                columns,
            )
        )
        if rate is not None:
            note = _rate_note(rate)
            if note:
                lines.append(f"    {note}")

    problems = validate_periods(day_pattern)
    if problems:
        lines.extend(f"  {problem.message}" for problem in problems)
    else:
        lines.append(
            f"  Coverage: complete. {len(day_pattern.periods)} periods, no gaps, "
            "no overlaps."
        )

    lines.append(render_export_row(plan, day_pattern, columns))
    return "\n".join(lines)


def render_unscheduled(plan: Plan, widths: tuple[int, int]) -> str:
    """Return rows for rates no time period names.

    A fallback used only past an allowance has no period of its own, so a table
    keyed on periods would drop it. It is still part of the plan and still gets
    published, so it gets a row with the time cell empty.
    """
    scheduled = {
        (day_pattern.name, period.rate)
        for day_pattern in plan.day_patterns
        for period in day_pattern.periods
    }
    rows = [
        _row(
            "",
            rate.name,
            qualified_name(plan.name, day_pattern.name, rate.name),
            _price(rate.import_price * 100),
            widths,
        )
        for day_pattern, rate in plan.rates_with_pattern()
        if (day_pattern.name, rate.name) not in scheduled
    ]
    return "\n".join(rows)


def render_plan(plan: Plan) -> str:
    """Render every timetable in the plan as one table each."""
    if not plan.rates:
        # Also covers there being no timetables at all: with rates nested
        # inside DayPattern (Gap #1), a plan with no timetables can never
        # have a rate either, so the two used-to-be-separate empty states
        # collapse into this one now.
        return "No rates entered yet."
    widths = column_widths(plan)
    body = "\n\n".join(
        render_day_pattern(plan, day_pattern, widths)
        for day_pattern in plan.day_patterns
    )
    unscheduled = render_unscheduled(plan, widths)
    if unscheduled:
        return f"{body}\n\nNot on any timetable\n{unscheduled}"
    return body


def render_rate_plan_card(plan: Plan) -> str:
    """Render the plan in the shape an inverter's own tariff screen asks for.

    Tesla, Sungrow, Fronius and GoodWe all have that screen. This renders the
    plan for transcription; nothing is written to any vendor.
    """
    lines: list[str] = [f"Rate plan: {plan.name}", ""]
    if plan.description:
        lines.extend([plan.description, ""])

    if plan.prices_include_gst:
        lines.append(f"Prices include tax at {plan.gst_percent:g}%.")
    else:
        lines.append("Prices exclude tax.")
    lines.append(f"Daily supply charge: {plan.daily_supply_charge * 100:.2f} c/day")
    if plan.monthly_charge:
        lines.append(f"Monthly charge: {plan.monthly_charge:.2f} per month")
    if plan.billing_cycle_day:
        lines.append(
            f"Billing cycle starts on day {plan.billing_cycle_day} of the month"
        )
    lines.append("")

    for day_pattern in plan.day_patterns:
        lines.append(f"{day_pattern.name} — {', '.join(sorted(day_pattern.days))}")
        if day_pattern.is_seasonal:
            assert day_pattern.season_from is not None
            assert day_pattern.season_to is not None
            lines.append(
                f"  Season {day_pattern.season_from[1]:02d}/{day_pattern.season_from[0]:02d}"
                f" to {day_pattern.season_to[1]:02d}/{day_pattern.season_to[0]:02d}"
            )
        for period in day_pattern.sorted_periods():
            rate = day_pattern.rate_by_name(period.rate)
            if rate is None:
                lines.append(
                    f"  {format_time(period.start)}-{format_time(period.end)}"
                    f"  {period.rate}  ({MISSING})"
                )
                continue
            identifier = qualified_name(plan.name, day_pattern.name, rate.name)
            lines.append(
                f"  {format_time(period.start)}-{format_time(period.end)}"
                f"  {identifier:<12}"
                f"  buy {rate.import_price:.4f}/kWh"
            )
            note = _rate_note(rate)
            if note:
                lines.append(f"    {note}")
        lines.append(f"  {render_export_row(plan, day_pattern).strip()}")
        lines.append("")

    return "\n".join(lines).rstrip()
