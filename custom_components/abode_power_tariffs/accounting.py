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
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, tzinfo

from .const import (
    ALLOWANCE_PERIOD_MONTH,
    DEFAULT_BILLING_CYCLE_DAY,
    DEMAND_BASIS_DAY,
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
    averages over. A zero interval — no declaration can produce one now that
    no instantaneous basis is offered — has no interval and returns None,
    rather than dividing by zero.

    The alignment is done on the wall clock and the fold resolved afterwards.
    Flooring an aware datetime would do wall-clock arithmetic and always land
    on the first pass of a repeated hour, so the 02:30 interval that comes
    round a second time would be given the first pass's start and every
    reading in it would be filed under an interval that closed an hour ago.
    """
    if interval_minutes <= 0:
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
    if start is None or interval_minutes <= 0:
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


def split_delta(
    delta_kwh: float,
    start: datetime,
    end: datetime,
    boundaries: Sequence[datetime],
) -> list[tuple[datetime, float]]:
    """Split one meter delta at every boundary it straddles.

    The meter reads a running total, so a reading tells us how much was drawn
    since the previous one but not when. A reading either side of a rate
    boundary used to be credited wholly to whichever rate happened to be in
    force when it arrived, which over-prices an evening peak or under-counts a
    cap by however much was drawn on the other side of the boundary. With no
    way to know, the honest estimate is that the draw was even across the time
    between the two readings.

    Returns ``(segment_end, kwh)`` pairs, one per stretch of real time between
    boundaries, the last ending at ``end``. A boundary exactly at ``end``
    belongs to the stretch before it, so the whole delta is returned before
    that instant. The shares are by real elapsed seconds, subtracted in UTC:
    two aware datetimes sharing a tzinfo subtract on the wall clock, and an
    interval that holds the repeated hour is two hours long to a meter and one
    to the wall clock.
    """
    if delta_kwh <= 0:
        return []
    start_utc = start.astimezone(UTC)
    end_utc = end.astimezone(UTC)
    total_seconds = (end_utc - start_utc).total_seconds()
    if total_seconds <= 0:
        # No time between the readings: there is nothing to divide by, and
        # the figure belongs to the moment it arrived.
        return [(end, delta_kwh)]
    edges = sorted(
        boundary
        for boundary in boundaries
        if start_utc < boundary.astimezone(UTC) <= end_utc
    )
    slices: list[tuple[datetime, float]] = []
    previous = start_utc
    for edge in edges:
        edge_utc = edge.astimezone(UTC)
        seconds = (edge_utc - previous).total_seconds()
        slices.append((edge, delta_kwh * seconds / total_seconds))
        previous = edge_utc
    remaining = (end_utc - previous).total_seconds()
    slices.append((end, delta_kwh * remaining / total_seconds))
    return slices


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
    # The interval that closed most recently, and what it measured. A meter
    # reading can arrive after its interval has closed — the tick noticed the
    # boundary at :00, the reading covering the tail lands at :05 — and that
    # energy belongs to the interval already measured. Keeping it lets the
    # tail raise the peak instead of being dropped or filed under the interval
    # now open.
    last_closed_kwh: float = 0.0
    last_closed_key: str | None = None
    # How long the open interval is, recorded when the rate was in force.
    # A ledger leaving force cannot ask its rate any more, and closing an
    # interval that completed at the boundary needs to know its length.
    interval_minutes: int = 0
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
        # A closed interval from the cycle the retailer has billed cannot
        # take a late tail into the new one; its peak is gone.
        self.last_closed_kwh = 0.0
        self.last_closed_key = None

    def close_interval(
        self, moment: datetime, interval_minutes: int, zone: tzinfo
    ) -> float:
        """Finish the interval in progress and return its average draw in kW.

        Only a completed interval is a peak candidate, so this is the only
        place a peak can move. The timestamp recorded is when the interval
        started, not when it closed, because the bill is built on the
        half-hour (or other interval) that reached the peak, not the instant
        it finished.

        The interval's key and energy are kept after the bucket is emptied.
        A reading that arrives a few minutes after the boundary still covers
        the tail of this interval, and without them that energy would have
        nowhere to go: it would either be dropped or inflate the interval now
        opening.
        """
        drawn = average_kw(self.interval_kwh, interval_minutes)
        self.last_closed_kwh = self.interval_kwh
        self.last_closed_key = self.interval_key
        self.interval_kwh = 0.0
        # The interval is finished; the caller opens the next one and sets its
        # key. Until then nothing is open, which is what ``credit_interval``
        # tests for when a reading arrives for the interval just closed.
        ended_key = self.interval_key
        self.interval_key = None
        if drawn > self.peak_kw:
            self.peak_kw = drawn
            # The key is the interval's UTC start, which is the instant the
            # bill is built on. Where a key was never recorded (a ledger
            # closed directly in a test), fall back to the wall clock.
            start: datetime | None = None
            if ended_key is not None:
                start = datetime.fromisoformat(ended_key).astimezone(zone)
            if start is None:
                # ``moment`` is the instant the interval closed (the
                # boundary), which is also the start of the next interval.
                start_moment = moment - timedelta(minutes=interval_minutes)
                start = interval_start(start_moment, interval_minutes, zone)
            self.peak_at = start if start is not None else moment
        return drawn

    def credit_interval(
        self,
        key: str,
        kwh: float,
        interval_minutes: int,
        moment: datetime,
        zone: tzinfo,
        *,
        live: bool = True,
    ) -> None:
        """Credit energy to the demand interval a moment falls in.

        Three cases, and only three. The interval is open and takes it. It
        has already closed — a reading arrived after the boundary it straddles
        — and the closed figure is raised, then the peak is tested again,
        because the interval the bill is built on may have been measured low.
        Or it is an interval this ledger no longer holds, and the energy is
        dropped: a part-finished interval its rate left in is discarded, never
        resurrected.

        ``live`` says the energy runs up to the moment of the reading rather
        than ending at a boundary behind it. Only a live stretch may open an
        interval the ledger has not seen: a stretch that ends at a boundary is
        energy the ledger was holding an interval for, so a missing one means
        it was discarded.
        """
        if live and self.interval_key is None and self.last_closed_key != key:
            # Nothing open and not the one just closed: this is the interval
            # the energy belongs to, and this reading is the first seen of it.
            self.interval_key = key
            self.interval_minutes = interval_minutes
        if self.interval_key == key:
            self.interval_kwh += kwh
            return
        if self.last_closed_key == key:
            self.credit_closed_interval(kwh, interval_minutes, zone)
            return
        if self.interval_key is not None and self.interval_key < key:
            # The clock moved past the interval this ledger was holding, so it
            # completed. Close it before the one this energy belongs to opens,
            # exactly as the refresh does. Keys are UTC instants in one fixed
            # format, so comparing the strings compares the moments.
            self.close_interval(moment, self.interval_minutes or interval_minutes, zone)
            self.interval_key = key
            self.interval_minutes = interval_minutes
            self.interval_kwh += kwh
        # Anything else is an interval this ledger no longer holds: a
        # part-finished interval its rate left in is discarded, never
        # resurrected from a reading that arrives late.

    def credit_closed_interval(
        self, kwh: float, interval_minutes: int, zone: tzinfo
    ) -> None:
        """Add a late tail to the interval that just closed, and re-test the peak.

        The interval was already a candidate when it closed, measured on the
        energy seen by then. Energy that arrives afterwards is real consumption
        from the same interval, so the figure is raised and the peak can move
        with it.
        """
        if self.last_closed_key is None:
            return
        self.last_closed_kwh += kwh
        drawn = average_kw(self.last_closed_kwh, interval_minutes)
        if drawn > self.peak_kw:
            self.peak_kw = drawn
            self.peak_at = datetime.fromisoformat(self.last_closed_key).astimezone(zone)


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
