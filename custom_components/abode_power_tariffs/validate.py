"""Validation of a plan. Pure module.

A plan that fails any of these cannot be saved. Every problem names the day set
and the hours involved, because "invalid configuration" is not a useful message
when six windows are on screen.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .const import ALL_DAY_TOKENS, MINUTES_PER_DAY
from .plan import DaySet, Plan, format_time


@dataclass(frozen=True, slots=True)
class Problem:
    """One validation failure."""

    scope: str
    message: str

    def __str__(self) -> str:
        """Return the problem as one line."""
        return f"{self.scope}: {self.message}" if self.scope else self.message


def validate_windows(day_set: DaySet) -> list[Problem]:
    """Check that a day set's windows tile the day exactly once."""
    problems: list[Problem] = []
    windows = day_set.sorted_windows()

    if not windows:
        return [Problem(day_set.name, "has no windows")]

    for window in windows:
        if window.end <= window.start:
            problems.append(
                Problem(
                    day_set.name,
                    f"{format_time(window.start)}-{format_time(window.end)} ends "
                    "before it starts",
                )
            )

    cursor = 0
    for window in windows:
        if window.start > cursor:
            problems.append(
                Problem(
                    day_set.name,
                    f"nothing covers {format_time(cursor)}-{format_time(window.start)}",
                )
            )
        elif window.start < cursor:
            problems.append(
                Problem(
                    day_set.name,
                    f"{format_time(window.start)}-{format_time(window.end)} overlaps "
                    f"the window ending {format_time(cursor)}",
                )
            )
        cursor = max(cursor, window.end)

    if cursor < MINUTES_PER_DAY:
        problems.append(
            Problem(day_set.name, f"nothing covers {format_time(cursor)}-24:00")
        )

    return problems


def validate_day_coverage(plan: Plan) -> list[Problem]:
    """Check that every day type resolves to exactly one day set."""
    problems: list[Problem] = []
    # Two probe dates a season apart catch a range that covers only part of the
    # year without walking all 366 days.
    probes = _season_probe_dates(plan)

    for token in ALL_DAY_TOKENS:
        for probe in probes:
            matches = [
                day_set.name
                for day_set in plan.day_sets
                if day_set.matches(token, probe)
            ]
            seasonal = [
                name
                for name in matches
                if _named(plan, name) is not None and _named(plan, name).is_seasonal  # type: ignore[union-attr]
            ]
            general = [name for name in matches if name not in seasonal]
            if not matches:
                problems.append(
                    Problem("", f"no day set covers {token} on {probe.isoformat()}")
                )
            elif len(seasonal) > 1:
                problems.append(
                    Problem(
                        "",
                        f"{token} on {probe.isoformat()} is claimed by more than one "
                        f"seasonal day set: {', '.join(sorted(seasonal))}",
                    )
                )
            elif not seasonal and len(general) > 1:
                problems.append(
                    Problem(
                        "",
                        f"{token} is claimed by more than one day set: "
                        f"{', '.join(sorted(general))}",
                    )
                )

    return problems


def _named(plan: Plan, name: str) -> DaySet | None:
    for day_set in plan.day_sets:
        if day_set.name == name:
            return day_set
    return None


def _season_probe_dates(plan: Plan) -> list[date]:
    """Return one date inside each declared season plus the four quarters."""
    year = 2001  # A non-leap year, so 02-29 never appears as a probe.
    probes = {date(year, month, 15) for month in (1, 4, 7, 10)}
    for day_set in plan.day_sets:
        for edge in (day_set.season_from, day_set.season_to):
            if edge is not None:
                month, day = edge
                probes.add(date(year, month, min(day, 28)))
    return sorted(probes)


def validate_rates(plan: Plan) -> list[Problem]:
    """Check rate references and allowance fallbacks."""
    problems: list[Problem] = []
    names = set(plan.rate_names)

    if not plan.rates:
        problems.append(Problem("", "the plan has no rates"))

    if len(names) != len(plan.rates):
        problems.append(Problem("", "two rates share a name"))

    for rate in plan.rates:
        if rate.has_allowance:
            if not rate.fallback_rate:
                problems.append(
                    Problem(
                        rate.name,
                        "has a daily allowance but no fallback rate for beyond it",
                    )
                )
            elif rate.fallback_rate not in names:
                problems.append(
                    Problem(rate.name, f"names a fallback rate '{rate.fallback_rate}' "
                            "that does not exist")
                )
            else:
                fallback = plan.rate_by_name(rate.fallback_rate)
                if fallback is not None and fallback.has_allowance:
                    problems.append(
                        Problem(
                            rate.name,
                            f"falls back to '{fallback.name}', which itself has an "
                            "allowance",
                        )
                    )

    for day_set in plan.day_sets:
        for window in day_set.windows:
            if window.rate not in names:
                problems.append(
                    Problem(
                        day_set.name,
                        f"{format_time(window.start)}-{format_time(window.end)} names "
                        f"a rate '{window.rate}' that does not exist",
                    )
                )

    return problems


def validate_plan(plan: Plan) -> list[Problem]:
    """Run every check and return all problems found."""
    problems: list[Problem] = []

    if not plan.day_sets:
        problems.append(Problem("", "the plan has no day sets"))

    problems.extend(validate_rates(plan))
    for day_set in plan.day_sets:
        problems.extend(validate_windows(day_set))
    problems.extend(validate_day_coverage(plan))

    if (
        plan.valid_from is not None
        and plan.valid_to is not None
        and plan.valid_to < plan.valid_from
    ):
        problems.append(Problem("", "the plan's validity ends before it starts"))

    return problems


def is_valid(plan: Plan) -> bool:
    """Return whether the plan passes every check."""
    return not validate_plan(plan)
