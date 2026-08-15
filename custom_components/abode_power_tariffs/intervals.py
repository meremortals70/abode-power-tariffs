"""Forward interval generation and boundary calculation. Pure module.

Periods are wall-clock times: a peak period is 16:00 local on both sides of a
daylight-saving transition. Intervals are real instants, so a 23-hour day is
short by an hour and a 25-hour day repeats one. Both are emitted without gaps,
overlaps or duplicates because the walk is done in UTC and each instant is
converted to local time before the plan is resolved.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, tzinfo
from typing import Any

from .const import MINUTES_PER_DAY
from .plan import Plan, Resolution

HolidayCheck = Callable[[date], bool]


@dataclass(frozen=True, slots=True)
class Interval:
    """One resolved slice of the forward horizon."""

    start: datetime
    end: datetime
    rate: str
    import_price: float
    export_price: float
    constraints: tuple[str, ...]
    coasting_permitted: bool
    allowance_kwh: float | None
    day_pattern: str

    @property
    def duration_minutes(self) -> int:
        """Return the interval length in whole minutes."""
        return int((self.end - self.start).total_seconds() // 60)

    def as_dict(self) -> dict[str, Any]:
        """Return the interval in the published service response shape."""
        return {
            "start_time": self.start.isoformat(),
            "end_time": self.end.isoformat(),
            "duration": self.duration_minutes,
            "per_kwh": round(self.import_price, 6),
            "export_per_kwh": round(self.export_price, 6),
            "rate": self.rate,
            "constraints": list(self.constraints),
            "coasting_permitted": self.coasting_permitted,
            "allowance_kwh": self.allowance_kwh,
            "day_pattern": self.day_pattern,
            "forecast": False,
        }

    def as_evcc_entry(self) -> dict[str, Any]:
        """Return the interval in the shape evcc reads from a forecast attribute."""
        return {
            "start": self.start.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "end": self.end.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "value": round(self.import_price, 6),
        }


def local_minutes(moment: datetime, zone: tzinfo) -> tuple[date, int]:
    """Return the local date and minute of the day for an instant."""
    local = moment.astimezone(zone)
    return local.date(), local.hour * 60 + local.minute


def resolve_at(
    plan: Plan,
    moment: datetime,
    zone: tzinfo,
    is_holiday: HolidayCheck,
) -> Resolution | None:
    """Resolve the plan at an instant."""
    day, minutes = local_minutes(moment, zone)
    return plan.resolve(day, minutes, is_holiday(day))


def next_boundary(
    plan: Plan,
    moment: datetime,
    zone: tzinfo,
    is_holiday: HolidayCheck,
    *,
    max_days: int = 3,
) -> datetime | None:
    """Return the next instant at which the resolved period changes.

    Walks forward over the wall-clock boundaries of today and the following
    days, converting each to an instant. A boundary that does not exist on a
    short day is skipped because the converted instant is not later than the
    one before it.
    """
    local_now = moment.astimezone(zone)
    day = local_now.date()

    for offset in range(max_days + 1):
        current_day = day + timedelta(days=offset)
        edges = plan.boundaries_for(current_day, is_holiday(current_day))
        if not edges:
            # No day set on this date; the next day may still have one.
            continue
        for edge in edges:
            if edge >= MINUTES_PER_DAY:
                candidate_day = current_day + timedelta(days=1)
                candidate_minutes = 0
            else:
                candidate_day = current_day
                candidate_minutes = edge
            candidate = datetime.combine(
                candidate_day,
                datetime.min.time(),
                tzinfo=zone,
            ) + timedelta(minutes=candidate_minutes)
            if candidate > moment:
                return candidate.astimezone(moment.tzinfo or zone)

    return None


def generate(  # noqa: PLR0913 - every argument is required to resolve a plan
    plan: Plan,
    start: datetime,
    zone: tzinfo,
    is_holiday: HolidayCheck,
    *,
    hours: int = 24,
    resolution_minutes: int = 30,
) -> list[Interval]:
    """Generate the forward interval series from an instant."""
    if resolution_minutes <= 0:
        raise ValueError("resolution_minutes must be positive")
    if hours <= 0:
        raise ValueError("hours must be positive")

    step = timedelta(minutes=resolution_minutes)
    # Align the first interval to the resolution grid in local time, so a
    # 30-minute series starts on the hour or the half hour.
    local_start = start.astimezone(zone)
    minute_of_day = local_start.hour * 60 + local_start.minute
    aligned_minute = (minute_of_day // resolution_minutes) * resolution_minutes
    cursor = (
        datetime.combine(local_start.date(), datetime.min.time(), tzinfo=zone)
        + timedelta(minutes=aligned_minute)
    )
    finish = start + timedelta(hours=hours)

    intervals: list[Interval] = []
    while cursor < finish:
        nxt = cursor + step
        resolution = resolve_at(plan, cursor, zone, is_holiday)
        if resolution is not None:
            intervals.append(
                Interval(
                    start=cursor,
                    end=nxt,
                    rate=resolution.rate.name,
                    import_price=resolution.rate.import_price,
                    export_price=resolution.rate.export_price,
                    constraints=tuple(sorted(resolution.rate.constraints)),
                    coasting_permitted=resolution.rate.coasting_permitted,
                    allowance_kwh=resolution.rate.daily_allowance_kwh,
                    day_pattern=resolution.day_pattern.name,
                )
            )
        cursor = nxt

    return intervals
