"""The 24-hour text strip. Pure module.

One line per day set, one character per 30 minutes. Shown on the Configure menu
and on every screen that touches windows, so a gap or an overlap is visible at
the moment it is made rather than at save.
"""

from __future__ import annotations

from .const import MINUTES_PER_DAY
from .plan import DaySet, Plan, format_time
from .validate import validate_windows

SLOT_MINUTES = 30
SLOTS = MINUTES_PER_DAY // SLOT_MINUTES

# Distinct at a glance in a proportional-blind monospace block, and readable in
# both light and dark themes.
BLOCKS = ("█", "░", "▒", "▓", "▚", "▞", "▙", "▟")
GAP = " "
CLASH = "!"

RULER = "        00    03    06    09    12    15    18    21    24"


def _rate_symbols(plan: Plan) -> dict[str, str]:
    return {
        rate.name: BLOCKS[index % len(BLOCKS)]
        for index, rate in enumerate(plan.rates)
    }


def render_day_set(plan: Plan, day_set: DaySet) -> str:
    """Render one day set as a strip, a legend line and a coverage line."""
    symbols = _rate_symbols(plan)
    slots = [GAP] * SLOTS
    labels: list[tuple[int, str]] = []

    for window in day_set.sorted_windows():
        symbol = symbols.get(window.rate, "?")
        first = window.start // SLOT_MINUTES
        last = min(SLOTS, -(-window.end // SLOT_MINUTES))
        for index in range(first, last):
            slots[index] = CLASH if slots[index] != GAP else symbol
        labels.append((first, window.rate))

    strip = "".join(slots)

    legend_chars = [" "] * SLOTS
    for position, name in labels:
        for offset, character in enumerate(name):
            if position + offset < SLOTS:
                legend_chars[position + offset] = character
    legend = "".join(legend_chars).rstrip()

    problems = validate_windows(day_set)
    if problems:
        coverage = "  " + "\n  ".join(problem.message for problem in problems)
    else:
        coverage = (
            f"  Coverage: complete. {len(day_set.windows)} windows, no gaps, "
            "no overlaps."
        )

    season = ""
    if day_set.is_seasonal:
        assert day_set.season_from is not None
        assert day_set.season_to is not None
        season = (
            f"  ({day_set.season_from[1]:02d}/{day_set.season_from[0]:02d}"
            f" - {day_set.season_to[1]:02d}/{day_set.season_to[0]:02d})"
        )

    return "\n".join(
        [
            f"{day_set.name}{season}",
            RULER,
            f"        {strip}",
            f"        {legend}",
            "",
            coverage,
        ]
    )


def render_plan(plan: Plan) -> str:
    """Render every day set in the plan."""
    if not plan.day_sets:
        return "No day sets configured yet."
    return "\n\n".join(render_day_set(plan, day_set) for day_set in plan.day_sets)


def render_rate_plan_card(plan: Plan) -> str:
    """Render the plan in the shape an inverter's own tariff screen asks for.

    Tesla, Sungrow, Fronius and GoodWe all have that screen. This renders the
    plan for transcription; nothing is written to any vendor.
    """
    lines: list[str] = [f"Rate plan: {plan.name}", ""]

    if plan.prices_include_gst:
        lines.append(f"Prices include GST at {plan.gst_percent:g}%.")
    else:
        lines.append("Prices exclude tax.")
    lines.append(f"Daily supply charge: {plan.daily_supply_charge * 100:.2f} c/day")
    lines.append("")

    for day_set in plan.day_sets:
        lines.append(f"{day_set.name} — {', '.join(sorted(day_set.days))}")
        if day_set.is_seasonal:
            assert day_set.season_from is not None
            assert day_set.season_to is not None
            lines.append(
                f"  Season {day_set.season_from[1]:02d}/{day_set.season_from[0]:02d}"
                f" to {day_set.season_to[1]:02d}/{day_set.season_to[0]:02d}"
            )
        for window in day_set.sorted_windows():
            rate = plan.rate_by_name(window.rate)
            if rate is None:
                lines.append(
                    f"  {format_time(window.start)}-{format_time(window.end)}"
                    f"  {window.rate}  (rate missing)"
                )
                continue
            lines.append(
                f"  {format_time(window.start)}-{format_time(window.end)}"
                f"  {rate.name:<12}"
                f"  buy {rate.import_price:.4f}/kWh"
                f"  sell {rate.export_price:.4f}/kWh"
            )
        lines.append("")

    return "\n".join(lines).rstrip()
