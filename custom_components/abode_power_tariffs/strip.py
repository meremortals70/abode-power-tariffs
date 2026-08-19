"""Rendering the plan as text. Pure module.

There used to be a coloured 24-hour bar here, drawn with emoji squares under a
character ruler. It could not be made to line up: the ruler is plain characters
and the squares are emoji, and their widths differ by font and platform, so the
bar drifted against the clock by hours on some browsers. A visual you cannot
read against the clock is worse than none.

So this renders the plan as plain text, which is exact everywhere, and the
picture is left to Home Assistant. `sensor.<name>_rate` is an enum, so a
built-in history-graph card draws it as a coloured timeline with a real time
axis. See the README.
"""

from __future__ import annotations

from .plan import DayPattern, Plan, format_time
from .validate import validate_periods

# "00:00-06:00" and the two spaces after it. The legend has no time column,
# so it pads by this much to put its prices in the same place.
TIME_COLUMN = 13


def name_width(plan: Plan) -> int:
    """Return the width the name column needs across the whole plan.

    One width for every block, so the price column lands in the same place
    wherever it appears. A fixed pad silently fails the moment a name is
    longer than it: the price is pushed right and the column bends around it.
    """
    widest = 0
    for rate in plan.rates:
        widest = max(widest, len(rate.name), len(rate.qualified_name))
    for day_pattern in plan.day_patterns:
        for period in day_pattern.periods:
            widest = max(widest, len(period.rate))
        for period in day_pattern.export_periods:
            widest = max(widest, len(period.rate))
    for export_rate in plan.export_rates:
        widest = max(widest, len(export_rate.name))
    return widest + 2


def render_legend(plan: Plan, width: int | None = None) -> str:
    """Return one line per rate, cheapest first, identifier then price."""
    pad = name_width(plan) if width is None else width
    return "\n".join(
        f"  {rate.qualified_name:<{pad + TIME_COLUMN}}"
        f"{rate.import_price * 100:>7.2f} c/kWh"
        for rate in sorted(plan.rates, key=lambda rate: rate.import_price)
    )


def render_export_row(
    plan: Plan, day_pattern: DayPattern, width: int | None = None
) -> str:
    """Return the feed-in side of one timetable as text."""
    pad = name_width(plan) if width is None else width
    if day_pattern.export_same_all_day:
        return f"  Feed-in: {day_pattern.export_flat_price * 100:.2f} c/kWh all day"

    lines = ["  Feed-in:"]
    for period in day_pattern.sorted_export_periods():
        rate = plan.export_rate_by_name(period.rate)
        price = "rate missing" if rate is None else f"{rate.price * 100:>7.2f} c/kWh"
        lines.append(
            f"    {format_time(period.start)}-{format_time(period.end)}"
            f"  {period.rate:<{pad - 2}}{price}"
        )
    return "\n".join(lines)


def render_day_pattern(
    plan: Plan, day_pattern: DayPattern, width: int | None = None
) -> str:
    """Render one timetable: its periods, what each costs, and its coverage."""
    pad = name_width(plan) if width is None else width
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
        rate = plan.rate_by_name(period.rate, day_pattern.name)
        price = (
            "rate missing" if rate is None else f"{rate.import_price * 100:>7.2f} c/kWh"
        )
        lines.append(
            f"  {format_time(period.start)}-{format_time(period.end)}"
            f"  {period.rate:<{pad}}{price}"
        )

    problems = validate_periods(day_pattern)
    if problems:
        lines.extend(f"  {problem.message}" for problem in problems)
    else:
        lines.append(
            f"  Coverage: complete. {len(day_pattern.periods)} periods, no gaps, "
            "no overlaps."
        )

    lines.append(render_export_row(plan, day_pattern, pad))
    return "\n".join(lines)


def render_plan(plan: Plan) -> str:
    """Render every timetable in the plan, then the rates."""
    if not plan.rates:
        return "No rates entered yet."
    pad = name_width(plan)
    legend = "Rates\n" + render_legend(plan, pad)
    if not plan.day_patterns:
        return f"No day patterns configured yet.\n\n{legend}"
    body = "\n\n".join(
        render_day_pattern(plan, day_pattern, pad) for day_pattern in plan.day_patterns
    )
    return f"{body}\n\n{legend}"


def render_rate_plan_card(plan: Plan) -> str:
    """Render the plan in the shape an inverter's own tariff screen asks for.

    Tesla, Sungrow, Fronius and GoodWe all have that screen. This renders the
    plan for transcription; nothing is written to any vendor.
    """
    lines: list[str] = [f"Rate plan: {plan.name}", ""]
    if plan.description:
        lines.extend([plan.description, ""])

    if plan.prices_include_gst:
        lines.append(f"Prices include GST at {plan.gst_percent:g}%.")
    else:
        lines.append("Prices exclude tax.")
    lines.append(f"Daily supply charge: {plan.daily_supply_charge * 100:.2f} c/day")
    if plan.monthly_charge:
        lines.append(f"Monthly charge: {plan.monthly_charge:.2f} per month")
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
            rate = plan.rate_by_name(period.rate, day_pattern.name)
            if rate is None:
                lines.append(
                    f"  {format_time(period.start)}-{format_time(period.end)}"
                    f"  {period.rate}  (rate missing)"
                )
                continue
            lines.append(
                f"  {format_time(period.start)}-{format_time(period.end)}"
                f"  {rate.name:<12}"
                f"  buy {rate.import_price:.4f}/kWh"
            )
        lines.append(f"  {render_export_row(plan, day_pattern).strip()}")
        lines.append("")

    return "\n".join(lines).rstrip()
