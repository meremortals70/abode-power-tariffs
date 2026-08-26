"""Rate allowance accounting. Pure module.

Some plans give a period free or discounted only up to a cap — three free hours
capped at 24 kWh, for instance. Past the cap, consumption is priced at a
nominated fallback rate.

The allowance belongs to the time slot, not to the day. Each occurrence of a
capped slot has its own; nothing is carried between slots, days or billing
cycles. Anything spanning them is the consumer's arithmetic, from the cap and
fallback this component always publishes.
"""

from __future__ import annotations

from dataclasses import dataclass

from .plan import DayPattern, Rate


@dataclass(frozen=True, slots=True)
class AllowanceState:
    """The effective rate once the allowance has been taken into account."""

    rate: Rate
    exhausted: bool
    used_kwh: float
    remaining_kwh: float | None

    @property
    def reason(self) -> str:
        """Return a short explanation for the trace.

        No live figures. The trace is published as a sensor attribute, so a
        number that moves with every meter reading rewrites the attribute, and
        the entity state with it, several times a minute for no gain. How much
        allowance is left is published properly by its own sensor.
        """
        if self.remaining_kwh is None:
            return "no allowance on this rate"
        if self.exhausted:
            return "allowance spent"
        return "within the allowance"


def apply(day_pattern: DayPattern, rate: Rate, used_kwh: float) -> AllowanceState:
    """Return the rate actually in force given this slot's consumption so far.

    ``day_pattern`` is the timetable ``rate`` is nested in — the fallback, if
    any, is looked up there. A rate is nested inside exactly one timetable
    now (Gap #1), so there is nowhere else a fallback of its own could live.
    """
    if not rate.has_allowance:
        return AllowanceState(
            rate=rate, exhausted=False, used_kwh=used_kwh, remaining_kwh=None
        )

    assert rate.rate_allowance_kwh is not None
    remaining = max(0.0, rate.rate_allowance_kwh - used_kwh)

    if remaining > 0:
        return AllowanceState(
            rate=rate, exhausted=False, used_kwh=used_kwh, remaining_kwh=remaining
        )

    fallback = (
        day_pattern.rate_by_name(rate.fallback_rate) if rate.fallback_rate else None
    )
    # Validation guarantees a fallback exists, but a plan can be loaded from
    # storage written by an older version, so fall back to the rate itself.
    return AllowanceState(
        rate=fallback or rate,
        exhausted=True,
        used_kwh=used_kwh,
        remaining_kwh=0.0,
    )


# A single reading-to-reading jump beyond this is treated the same as a
# meter reset — implausible, not a real measurement. Real energy monitors
# push updates at least every few minutes; even a very large service (say
# 400A three-phase, roughly 250kW) drawing continuously for a full hour
# between two readings comes nowhere near this. Generous on purpose: this
# exists to catch a swapped-out meter entity or a hardware fault reporting
# something absurd, not to second-guess a genuinely large household.
MAX_PLAUSIBLE_DELTA_KWH = 10_000.0


def accumulate(
    previous_total: float | None, new_total: float | None, used_kwh: float
) -> float:
    """Add the delta of a monotonic energy meter to this slot's usage.

    A meter that resets, or that reports nothing, contributes nothing rather
    than a spurious negative or a spike. A spike is not hypothetical: a
    meter entity swapped out from under this component mid-session, or a
    genuine hardware fault, produces exactly this — a single reading that
    jumps by an amount no real household or small building draws between
    two consecutive readings, silently accepted forever afterward because
    a positive delta was the only thing ever checked for. The ceiling here
    is deliberately generous — real energy monitors update at least every
    few minutes, so even a very large service drawing continuously at its
    limit for an hour falls well under it — not tuned to any one
    installation's actual usage.
    """
    if previous_total is None or new_total is None:
        return used_kwh
    delta = new_total - previous_total
    if delta <= 0 or delta > MAX_PLAUSIBLE_DELTA_KWH:
        return used_kwh
    return used_kwh + delta
