"""Billing cycle and demand interval arithmetic. Pure module.

Every reset in this component is a wall-clock event that has to be recognised
in real time. The billing cycle rolls at local midnight on the billing cycle
day; a demand interval runs on the local clock, on the hour and on the half
hour, because that is what the meter averages over.

Nothing here subtracts two aware datetimes that share a tzinfo. Python compares
those on the wall clock, and on the morning the clocks go back the same wall
clock minute names two real instants an hour apart. Identity is carried by a
key built from a calendar date or from a UTC instant, and two keys are compared
for equality rather than two moments for difference — a key cannot be wrong by
an hour.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, tzinfo

from .const import (
    ALLOWANCE_PERIOD_MONTH,
    DEFAULT_BILLING_CYCLE_DAY,
    DEMAND_BASIS_DAY,
    DEMAND_INTERVAL_INSTANTANEOUS,
    MINUTES_PER_DAY,
)
from .intervals import instants_at


def _cycle_day(billing_cycle_day: int | None) -> int:
    """Return the day of the month a cycle starts on.

    A plan that never declared one bills from the first, which is what a
    retailer does in the absence of anything else. Days past 28 do not exist
    in February and are refused at declaration; a stored plan carrying one is
    clamped rather than crashing a reset.
    """
    if not billing_cycle_day:
        return DEFAULT_BILLING_CYCLE_DAY
    return max(1, min(28, int(billing_cycle_day)))


def cycle_start(day: date, billing_cycle_day: int | None) -> date:
    """Return the first calendar day of the billing cycle containing ``day``."""
    start_day = _cycle_day(billing_cycle_day)
    if day.day >= start_day:
        return date(day.year, day.month, start_day)
    # Before the billing day, so the cycle began in the previous month.
    year = day.year if day.month > 1 else day.year - 1
    month = day.month - 1 if day.month > 1 else 12
    return date(year, month, start_day)


def cycle_end(day: date, billing_cycle_day: int | None) -> date:
    """Return the last calendar day of the cycle containing ``day``.

    Inclusive. The day before the next cycle starts.
    """
    start = cycle_start(day, billing_cycle_day)
    year = start.year if start.month < 12 else start.year + 1
    month = start.month + 1 if start.month < 12 else 1
    length = monthrange(year, month)[1]
    next_start = date(year, month, min(start.day, length))
    return date.fromordinal(next_start.toordinal() - 1)


def days_in_cycle(day: date, billing_cycle_day: int | None) -> int:
    """Return the number of calendar days in the cycle containing ``day``.

    Calendar days, not 24-hour spans (rule 4). The cycle containing a
    daylight-saving transition holds one 23-hour day or one 25-hour day and
    still has exactly as many days as the calendar says it does. A demand
    charge billed per kW per day multiplies by this number, so counting real
    time here would bill a household an hour more or less than the retailer.
    """
    start = cycle_start(day, billing_cycle_day)
    end = cycle_end(day, billing_cycle_day)
    return end.toordinal() - start.toordinal() + 1


def days_elapsed_in_cycle(day: date, billing_cycle_day: int | None) -> int:
    """Return how many calendar days of the cycle have begun, ``day`` included."""
    return day.toordinal() - cycle_start(day, billing_cycle_day).toordinal() + 1


def cycle_key(day: date, billing_cycle_day: int | None) -> str:
    """Identify one billing cycle.

    Two figures belong to the same cycle when their keys match. A peak restored
    across a restart is only still true if it was set inside the cycle running
    now, and this is what says so — a comparison of two dates would have to
    decide what "the same month" means when the cycle starts on the 12th.
    """
    return cycle_start(day, billing_cycle_day).isoformat()


def interval_start(
    moment: datetime, interval_minutes: int, zone: tzinfo
) -> datetime | None:
    """Return the real instant the demand interval containing ``moment`` began.

    Clock-aligned, not meter-aligned: a 30-minute interval runs 00:00–00:30,
    00:30–01:00 and so on down the local clock, which is the grid the retailer
    averages over. An instantaneous declaration has no interval and returns
    None.

    The alignment is done on the wall clock and the fold resolved afterwards.
    Flooring an aware datetime would do wall-clock arithmetic and always land
    on the first pass of a repeated hour, so the 02:30 interval that comes
    round a second time would be given the first pass's start and every
    reading in it would be filed under an interval that closed an hour ago.
    """
    if interval_minutes <= DEMAND_INTERVAL_INSTANTANEOUS:
        return None
    local = moment.astimezone(zone)
    minutes = (local.hour * 60 + local.minute) // interval_minutes * interval_minutes
    candidates = [
        candidate
        for candidate in instants_at(local.date(), minutes, zone)
        if candidate.astimezone(UTC) <= moment.astimezone(UTC)
    ]
    if not candidates:
        return None
    # The latest start that has actually happened. Inside the second pass of a
    # repeated hour both instants qualify and the later one is the live one.
    return max(candidates, key=lambda candidate: candidate.astimezone(UTC))


def interval_key(moment: datetime, interval_minutes: int, zone: tzinfo) -> str | None:
    """Identify one occurrence of one demand interval.

    A UTC instant, so the two passes through a repeated hour are two different
    intervals and the second cannot be mistaken for a continuation of the
    first.
    """
    start = interval_start(moment, interval_minutes, zone)
    if start is None:
        return None
    return start.astimezone(UTC).isoformat()


def interval_is_complete(
    moment: datetime, start: datetime | None, interval_minutes: int
) -> bool:
    """Return whether the interval that began at ``start`` has finished.

    Compared in UTC. An interval only becomes a peak candidate once complete,
    because a half-finished one has had less time to accumulate and always
    reads low — a partial interval at a slot boundary would otherwise drag a
    peak down and report a demand charge lower than the bill.
    """
    if start is None or interval_minutes <= DEMAND_INTERVAL_INSTANTANEOUS:
        return False
    elapsed = (moment.astimezone(UTC) - start.astimezone(UTC)).total_seconds()
    return elapsed >= interval_minutes * 60


def slot_key(qualified_name: str, start: int, end: int, day: date) -> str:
    """Identify one occurrence of one capped slot.

    The rate, the period within the day, and the date. Two periods naming the
    same rate on one day are two slots with an allowance each; the same period
    tomorrow is a different occurrence. This is rule 8 written down.
    """
    return f"{qualified_name}@{start}-{end}/{day.isoformat()}"


def allowance_key(
    qualified_name: str,
    period: str,
    start: int,
    end: int,
    day: date,
    billing_cycle_day: int | None,
) -> str:
    """Identify the accounting period one allowance count belongs to.

    A timed allowance belongs to the slot occurrence and nothing else — the
    owner's hard rule, unchanged. A monthly one belongs to the billing cycle
    and carries across every slot and day inside it.
    """
    if period == ALLOWANCE_PERIOD_MONTH:
        return f"{qualified_name}/cycle/{cycle_key(day, billing_cycle_day)}"
    return slot_key(qualified_name, start, end, day)


def demand_cost(
    peak_kw: float,
    rate_per_kw: float,
    basis: str,
    days: int,
) -> float:
    """Return what a peak costs on the declared basis.

    Flat: the peak is charged once for the billing period. Per day: charged for
    every day of it. The same 5 kW peak at 20 c is $1.00 or $31.00 over a
    31-day cycle, which is why the basis is asked for rather than assumed.
    """
    if peak_kw <= 0 or rate_per_kw <= 0:
        return 0.0
    if basis == DEMAND_BASIS_DAY:
        return round(peak_kw * rate_per_kw * max(0, days), 6)
    return round(peak_kw * rate_per_kw, 6)


def average_kw(energy_kwh: float, interval_minutes: int) -> float:
    """Return the average draw over a completed interval, in kW.

    The meter reports energy; a demand charge is priced on power. Over half an
    hour, 2.5 kWh is 5 kW.
    """
    if interval_minutes <= 0 or energy_kwh <= 0:
        return 0.0
    return round(energy_kwh * 60.0 / interval_minutes, 6)


@dataclass(slots=True)
class RateLedger:
    """What one rate has accumulated, and which period each figure belongs to.

    One of these per rate, keyed on the qualified identifier, because rule 10
    says a rate is its timetable plus its name. A ledger per plan is what threw
    energy away at a slot boundary: the count was zeroed the moment the
    resolution moved, and the reading taken just before it had already been
    added to it. Here the delta is credited to the rate it was drawn under, and
    a different rate coming into force touches nothing on this one.
    """

    qualified_name: str
    # The allowance count, and the period it belongs to. When the period key
    # changes the count starts again; nothing carries between occurrences.
    allowance_used_kwh: float = 0.0
    allowance_key: str | None = None
    # What the count reached when its period last closed. Kept so a closing
    # figure is superseded rather than discarded, and so a restart landing in
    # a new period can still say what the previous one came to.
    allowance_closed_kwh: float = 0.0
    # Energy drawn so far inside the demand interval in progress.
    interval_kwh: float = 0.0
    interval_key: str | None = None
    # The highest completed interval this billing cycle, and when it was set.
    peak_kw: float = 0.0
    peak_at: datetime | None = None
    peak_cycle: str | None = None
    # Whether an input gap has been seen while this cycle was running.
    incomplete: bool = False
    trace: tuple[str, ...] = field(default_factory=tuple)

    def roll_allowance(self, key: str) -> None:
        """Start a new allowance period, keeping what the last one came to."""
        if self.allowance_key == key:
            return
        if self.allowance_key is not None:
            self.allowance_closed_kwh = self.allowance_used_kwh
        self.allowance_key = key
        self.allowance_used_kwh = 0.0

    def roll_cycle(self, key: str) -> None:
        """Start a new billing cycle. The peak and the red flag both clear."""
        if self.peak_cycle == key:
            return
        self.peak_cycle = key
        self.peak_kw = 0.0
        self.peak_at = None
        self.incomplete = False

    def close_interval(self, moment: datetime, interval_minutes: int) -> float:
        """Finish the interval in progress and return its average draw in kW.

        Only a completed interval is a peak candidate, so this is the only
        place a peak can move.
        """
        drawn = average_kw(self.interval_kwh, interval_minutes)
        self.interval_kwh = 0.0
        if drawn > self.peak_kw:
            self.peak_kw = drawn
            self.peak_at = moment
        return drawn


def midnight_instants(day: date, zone: tzinfo) -> tuple[datetime, ...]:
    """Return every real instant local midnight names on a date.

    Ordinarily one. A zone whose transition happens at midnight names it twice
    or not at all, and a cycle reset scheduled on the wall clock alone would
    fire twice or be skipped.
    """
    return instants_at(day, 0, zone)


def cycle_reset_instant(
    day: date, billing_cycle_day: int | None, zone: tzinfo
) -> datetime | None:
    """Return the instant the cycle containing ``day`` began.

    The first real instant of the billing day. Built through ``instants_at`` so
    a transition at midnight resolves to a real moment rather than to a wall
    clock reading that never happened.
    """
    instants = midnight_instants(cycle_start(day, billing_cycle_day), zone)
    return instants[0] if instants else None


def minutes_of_day(moment: datetime, zone: tzinfo) -> int:
    """Return the local minute of the day, 0 to 1439."""
    local = moment.astimezone(zone)
    return (local.hour * 60 + local.minute) % MINUTES_PER_DAY
