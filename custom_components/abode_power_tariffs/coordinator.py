"""Runtime state for one tariff channel.

There is no polling. The next period boundary is computed and scheduled; on
firing, entities update and the following boundary is scheduled. A tick on the
zero second of every minute recomputes, so a reset lands on the minute it is
due without anything being load-bearing.

The component accounts. A declared cap is counted and a declared demand charge
is measured, per rate and keyed on the qualified identifier, because a source
of truth that declares a cap cannot state the current tariff without knowing
whether the cap is spent. What comes out of that is an estimate this component
measured itself: it will not reconcile with a bill, and every accumulating
entity says so.

Every reset is driven by comparing keys rather than by subtracting datetimes.
Two aware datetimes sharing a tzinfo subtract on the wall clock, which is an
hour wrong twice a year, and this is the first place in the component where
that costs money rather than display.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)
from homeassistant.util import dt as dt_util

from . import accounting as accounting_module
from . import allowance as allowance_module
from . import intervals as intervals_module
from . import plan as plan_module
from .const import (
    CONF_EXPORT_ENERGY_SENSOR,
    CONF_HOLIDAY_SENSOR,
    CONF_IMPORT_ENERGY_SENSOR,
    CONF_TARIFF_SELECTS,
    DOMAIN,
    ISSUE_DATA_GAP,
    ISSUE_PLAN_EXPIRED,
    SIGNAL_UPDATE,
)
from .plan import ExportResolution, Plan, Rate, Resolution
from .validate import validate_plan

_LOGGER = logging.getLogger(__name__)

UNUSABLE = (STATE_UNAVAILABLE, STATE_UNKNOWN, None, "")


def _allowance_slot(
    qualified_name: str,
    allowance_period: str,
    period_start: int,
    period_end: int,
    day: date,
    cycle_day: int | None,
) -> str:
    """Identify the accounting period this rate's allowance count belongs to.

    A timed allowance belongs to the slot occurrence — the rate, the period
    within the day and the date — and to nothing else. Two periods naming the
    same rate on one day are two slots with an allowance each; the same period
    tomorrow is a different occurrence. That is rule 8 and it is unchanged.

    A monthly allowance is its sibling: it belongs to the billing cycle and
    carries across every slot and day inside it. Takes the qualified name and
    period bounds directly rather than a Resolution, so the same function
    serves both the import side (which always has one) and the export side
    (which only has a named rate and a period on a period-priced timetable).
    """
    return accounting_module.allowance_key(
        qualified_name, allowance_period, period_start, period_end, day, cycle_day
    )


@dataclass(slots=True)
class TariffState:
    """Everything the entities read, recomputed at each boundary."""

    resolution: Resolution | None = None
    effective_rate: Rate | None = None
    allowance_used_kwh: float = 0.0
    allowance_remaining_kwh: float | None = None
    allowance_exhausted: bool = False
    # Which occurrence of which capped slot the count above belongs to. The
    # allowance is the slot's, not the day's, so this and not the calendar is
    # what says whether a count is still live.
    allowance_slot: str | None = None
    next_change: datetime | None = None
    next_export_change: datetime | None = None
    plan_expired: bool = False
    trace: tuple[str, ...] = ()

    # The export mirror of the five fields above (Gap #4). None throughout
    # when the export side resolves to a flat all-day price with no named
    # rate — there is nothing to meter or cap in that case, only the
    # timetable's own declared flat price.
    export_resolution: ExportResolution | None = None
    export_effective_price: float | None = None
    export_allowance_used_kwh: float = 0.0
    export_allowance_remaining_kwh: float | None = None
    export_allowance_exhausted: bool = False
    export_allowance_slot: str | None = None

    # One ledger per rate, keyed on the qualified identifier. Per rate and not
    # per plan: a single plan-wide counter is what credited energy to the slot
    # being left and then zeroed it on the way in to the next one. Import and
    # export rates never share a ledger, because the identifier itself says
    # which side a rate is on (Gap #4).
    ledgers: dict[str, accounting_module.RateLedger] = field(default_factory=dict)

    # The billing cycle, recomputed on every refresh. Every monthly reset is
    # driven off the key rather than off a date comparison.
    cycle_key: str = ""
    cycle_start: date | None = None
    cycle_end: date | None = None
    days_elapsed: int = 0
    days_in_cycle: int = 0

    # Supply charge accrued so far, in dollars. Reinstated with rule 11.
    supply_charge_today: float = 0.0
    supply_charge_cycle: float = 0.0
    # The calendar day the daily charge last landed for (Gap #5). Compared by
    # key, the same way every other reset in this component is, rather than
    # by subtracting two aware datetimes that share a tzinfo.
    supply_charge_day: date | None = None

    # Whether every input has been readable for the whole of this cycle.
    # Recovery does not retrieve what was missed, so the flag stays up until
    # the cycle rolls.
    data_complete: bool = True
    cycle_complete: bool = True
    gap_since: datetime | None = None
    gap_minutes: float = 0.0


class TariffCoordinator:
    """Holds the plan, resolves it, and tells the entities when it changed."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        plan: Plan,
        options: dict[str, Any],
    ) -> None:
        """Initialise the coordinator."""
        self.hass = hass
        self.entry_id = entry_id
        self.plan = plan
        self.options = options
        self.state = TariffState()

        self._unsubscribes: list[CALLBACK_TYPE] = []
        self._boundary_unsubscribe: CALLBACK_TYPE | None = None
        self._last_energy_total: float | None = None
        self._last_export_energy_total: float | None = None
        self._last_written_tariff: str | None = None
        self._holiday_warned = False
        self._energy_warned = False
        self._export_energy_warned = False
        self._expired_warned = False
        self._gap_reason = ""
        self._forward_key: tuple[Any, ...] | None = None
        self._forward_series: list[intervals_module.Interval] = []

    # ------------------------------------------------------------------ setup

    async def async_start(self) -> None:
        """Begin tracking. Called once, from async_setup_entry."""
        holiday_entity = self.options.get(CONF_HOLIDAY_SENSOR)
        energy_entity = self.options.get(CONF_IMPORT_ENERGY_SENSOR)
        export_energy_entity = self.options.get(CONF_EXPORT_ENERGY_SENSOR)

        tracked = [
            entity
            for entity in (holiday_entity, energy_entity, export_energy_entity)
            if entity
        ]
        if tracked:
            self._unsubscribes.append(
                async_track_state_change_event(
                    self.hass, tracked, self._handle_state_change
                )
            )

        # Recompute on the zero second of every minute. Boundaries are whole
        # minutes, so a tick lands on each one exactly, and resolve_at works
        # forwards from the current instant so it is already right inside a
        # repeated hour. Nothing is then load-bearing: a wrong scheduled
        # instant costs a minute rather than hours. A tick that changes
        # nothing writes nothing, because async_write_ha_state is a no-op on
        # an unchanged value.
        self._unsubscribes.append(
            async_track_time_change(self.hass, self.async_refresh, second=0)
        )

        self._seed_energy_total()
        self.async_refresh()

    @callback
    def async_shutdown(self) -> None:
        """Cancel every listener. Called from async_unload_entry."""
        for unsubscribe in self._unsubscribes:
            unsubscribe()
        self._unsubscribes.clear()
        if self._boundary_unsubscribe is not None:
            self._boundary_unsubscribe()
            self._boundary_unsubscribe = None

    # -------------------------------------------------------------- resolving

    @property
    def counting_allowance(self) -> bool:
        """Return whether this channel is counting against declared caps.

        There is no opt-in. Rule 7 was revoked: a plan that declares a cap has
        it counted, because declaring a cap and refusing to count it means
        publishing a price that may already be wrong. The import meter is
        mandatory now (Gap #7, rule 6 revoked) rather than required only once
        a declaration makes it necessary, so this is true for every plan that
        has actually completed setup; the check is kept as a guard for a plan
        stored before that became true, which should count nothing rather
        than crash on a meter that was never asked for.

        What is published from that count is an estimate this component
        measured itself. It will not agree exactly with a retailer counting it
        their own way, and every accumulating entity says so.
        """
        return bool(self.options.get(CONF_IMPORT_ENERGY_SENSOR))

    @property
    def counting_export_allowance(self) -> bool:
        """Return whether this channel is counting against export declarations.

        The export mirror of ``counting_allowance`` (Gap #4). Unlike the
        import meter, the export meter stays optional (rule 6 only ever
        applied to import) — a plan can export without any export rate
        declaring a demand charge or an allowance, and nothing needs
        counting in that case.
        """
        return bool(self.options.get(CONF_EXPORT_ENERGY_SENSOR))

    @property
    def accounts(self) -> bool:
        """Return whether anything in this plan is worth accumulating for."""
        importing = self.counting_allowance and any(
            rate.has_allowance or rate.has_demand_charge for rate in self.plan.rates
        )
        exporting = self.counting_export_allowance and any(
            rate.has_allowance or rate.has_demand_charge
            for rate in self.plan.export_rates
        )
        return importing or exporting

    def _known_qualified_names(self) -> set[str]:
        """Return every identifier a ledger could legitimately exist for."""
        import_names = {
            plan_module.qualified_name(self.plan.name, day_pattern.name, rate.name)
            for day_pattern, rate in self.plan.rates_with_pattern()
        }
        export_names = {
            plan_module.qualified_name(
                self.plan.name, day_pattern.name, rate.name, export=True
            )
            for day_pattern, rate in self.plan.export_rates_with_pattern()
        }
        return import_names | export_names

    def ledger_for(
        self, qualified_name: str | None
    ) -> accounting_module.RateLedger | None:
        """Return a ledger by identifier, creating it if the rate exists.

        Used by the restore paths, which run before the first refresh and so
        cannot rely on a ledger having been made yet. An identifier that
        belongs to neither an import nor an export rate in the current plan
        — a stale restored entity after an edit removed the rate it was for
        — gets nothing rather than an orphaned ledger.
        """
        if qualified_name is None:
            return None
        if qualified_name not in self._known_qualified_names():
            return None
        return self.ledger(qualified_name)

    def ledger(self, qualified_name: str) -> accounting_module.RateLedger:
        """Return this rate's ledger, creating it on first use.

        Keyed on the qualified identifier, never on the bare name. Two
        timetables can each carry a Peak, and a dict keyed on the name would
        put both households' worth of energy in one place — the exact fault
        that turned two timetables into one colour in strip.py. Import and
        export rates of the same name on the same timetable are two more
        things that must never collapse into one ledger (Gap #4), which is
        why the identifier itself now carries which side a rate is on.
        """
        existing = self.state.ledgers.get(qualified_name)
        if existing is None:
            existing = accounting_module.RateLedger(qualified_name)
            self.state.ledgers[qualified_name] = existing
        return existing

    @property
    def zone(self) -> Any:
        """Return Home Assistant's configured time zone."""
        return dt_util.get_default_time_zone()

    def is_holiday(self, day: date) -> bool:
        """Return whether a date is a public holiday.

        Only today can be answered, because the nominated binary sensor reports
        one day at a time. Other dates are treated as ordinary, which is the
        same answer as having no sensor at all.
        """
        entity_id = self.options.get(CONF_HOLIDAY_SENSOR)
        if not entity_id:
            return False
        if day != dt_util.now().date():
            return False
        state = self.hass.states.get(entity_id)
        if state is None or state.state in UNUSABLE:
            if not self._holiday_warned:
                _LOGGER.warning(
                    "Holiday sensor %s is unavailable; treating today as an ordinary day",
                    entity_id,
                )
                self._holiday_warned = True
            return False
        if self._holiday_warned:
            _LOGGER.info("Holiday sensor %s is available again", entity_id)
            self._holiday_warned = False
        # A workday sensor is on when it is a working day, so a public holiday
        # is the off state. The option is documented as a holiday sensor, so
        # the inversion is applied here rather than asked of the user.
        is_working_day: bool = state.state == STATE_ON
        return not is_working_day

    @callback
    def async_refresh(self, _now: datetime | None = None) -> None:
        """Recompute the state and tell the entities."""
        now = dt_util.now()
        today = now.date()
        trace: list[str] = []

        self.state.plan_expired = not self.plan.is_active_on(today)
        if self.state.plan_expired:
            trace.append("plan validity has passed; holding the expired plan")
            self._open_expired_issue()
        else:
            self._close_expired_issue()

        resolution = intervals_module.resolve_at(
            self.plan, now, self.zone, self.is_holiday
        )
        self.state.resolution = resolution
        export_resolution = self.export_resolution_now()
        self.state.export_resolution = export_resolution

        # The cycle first: every monthly reset below is driven off this key,
        # and a ledger rolled against a stale one keeps a peak that belongs to
        # a month the retailer has already billed.
        self._refresh_cycle(today)

        active_qualified_names: set[str] = set()

        if resolution is None:
            self.state.effective_rate = None
            trace.append("no period resolves at this moment")
        else:
            trace.append(f"day set {resolution.day_pattern.name}")
            active_qualified_names.add(resolution.qualified_name)
            slot = _allowance_slot(
                resolution.qualified_name,
                resolution.rate.allowance_period,
                resolution.period.start,
                resolution.period.end,
                today,
                self.plan.billing_cycle_day,
            )
            self.state.allowance_slot = slot
            ledger = self.ledger(resolution.qualified_name)
            # A different slot occurrence, or a new billing cycle for a
            # monthly cap. The count starts again and what it reached is kept
            # rather than dropped on the floor.
            ledger.roll_allowance(slot)
            self._refresh_interval(
                now,
                ledger,
                resolution.rate.has_demand_charge,
                resolution.rate.demand_interval,
            )

            if self.counting_allowance:
                self.state.allowance_used_kwh = ledger.allowance_used_kwh
                allowance_state = allowance_module.apply(
                    resolution.day_pattern, resolution.rate, ledger.allowance_used_kwh
                )
                self.state.effective_rate = allowance_state.rate
                self.state.allowance_remaining_kwh = allowance_state.remaining_kwh
                self.state.allowance_exhausted = allowance_state.exhausted
                trace.append(allowance_state.reason)
                if allowance_state.exhausted:
                    trace.append(f"priced at {allowance_state.rate.name}")
            else:
                # A declared cap with no meter to count it against. The
                # import meter is mandatory now (Gap #7, rule 6 revoked), so
                # this is a plan stored before that became true, or one whose
                # meter has since been removed: the price is the scheduled
                # one and the cap and fallback are published for a consumer
                # to apply itself.
                self.state.allowance_used_kwh = 0.0
                self.state.effective_rate = resolution.rate
                self.state.allowance_remaining_kwh = None
                self.state.allowance_exhausted = False
                if resolution.rate.has_allowance:
                    trace.append("capped, but no meter is nominated to count it")

        # The export mirror of the block above (Gap #4). Only a period-priced
        # timetable naming an export rate has anything to meter or cap — a
        # flat all-day price has no rate object of its own, only the
        # timetable's own declared flat price, cap and fallback.
        if export_resolution is None or export_resolution.rate_name is None:
            self.state.export_effective_price = (
                None if export_resolution is None else export_resolution.pricing.price
            )
            self.state.export_allowance_used_kwh = 0.0
            self.state.export_allowance_remaining_kwh = None
            self.state.export_allowance_exhausted = False
            self.state.export_allowance_slot = None
        else:
            export_rate = export_resolution.day_pattern.export_rate_by_name(
                export_resolution.rate_name
            )
            assert export_rate is not None
            assert export_resolution.period is not None
            qname = export_resolution.qualified_name
            assert qname is not None
            active_qualified_names.add(qname)
            export_ledger = self.ledger(qname)
            export_slot = _allowance_slot(
                qname,
                # An export rate's allowance is always slot-scoped: it has no
                # allowance_period declaration of its own, unlike an import
                # rate. See ExportRate — a monthly export cap was not part of
                # this build's scope.
                "slot",
                export_resolution.period.start,
                export_resolution.period.end,
                today,
                self.plan.billing_cycle_day,
            )
            self.state.export_allowance_slot = export_slot
            export_ledger.roll_allowance(export_slot)
            self._refresh_interval(
                now,
                export_ledger,
                export_rate.has_demand_charge,
                export_rate.demand_interval,
            )

            if self.counting_export_allowance and export_rate.has_allowance:
                self.state.export_allowance_used_kwh = export_ledger.allowance_used_kwh
                assert export_rate.allowance_kwh is not None
                remaining = max(
                    0.0,
                    export_rate.allowance_kwh - export_ledger.allowance_used_kwh,
                )
                exhausted = remaining <= 0
                self.state.export_allowance_remaining_kwh = remaining
                self.state.export_allowance_exhausted = exhausted
                self.state.export_effective_price = (
                    export_rate.fallback_price
                    if exhausted and export_rate.fallback_price is not None
                    else export_rate.price
                )
            else:
                self.state.export_allowance_used_kwh = 0.0
                self.state.export_allowance_remaining_kwh = None
                self.state.export_allowance_exhausted = False
                self.state.export_effective_price = export_rate.price

        self._leave_intervals_except(active_qualified_names)
        self._refresh_supply_charge(now, today)

        # Two separate facts. The import rate can be flat all day while the
        # feed-in price moves, and a consumer weighing an export against a
        # cheaper import later needs to know which of the two is changing.
        self.state.next_change = intervals_module.next_boundary(
            self.plan, now, self.zone, self.is_holiday
        )
        self.state.next_export_change = intervals_module.next_boundary(
            self.plan, now, self.zone, self.is_holiday, export=True
        )
        self.state.trace = tuple(trace)

        self._schedule_next_boundary()
        self._async_write_tariff_selects()
        async_dispatcher_send(self.hass, f"{SIGNAL_UPDATE}_{self.entry_id}")

    # ------------------------------------------------------------ accounting

    def _refresh_cycle(self, today: date) -> None:
        """Recompute the billing cycle and roll anything the roll clears.

        Identity by key. Asking whether two dates are "the same month" has no
        good answer when the cycle starts on the 12th, and subtracting two
        local datetimes to find out is an hour wrong twice a year.
        """
        cycle_day = self.plan.billing_cycle_day
        key = accounting_module.cycle_key(today, cycle_day)
        rolled = key != self.state.cycle_key

        self.state.cycle_key = key
        self.state.cycle_start = accounting_module.cycle_start(today, cycle_day)
        self.state.cycle_end = accounting_module.cycle_end(today, cycle_day)
        # Calendar days, not 24-hour spans (rule 4). A per-day demand charge
        # multiplies by this, so counting real time would bill an hour more or
        # less than the retailer in the month a transition falls.
        self.state.days_in_cycle = accounting_module.days_in_cycle(today, cycle_day)
        self.state.days_elapsed = accounting_module.days_elapsed_in_cycle(
            today, cycle_day
        )

        for ledger in self.state.ledgers.values():
            ledger.roll_cycle(key)
        if rolled:
            # Recovery does not retrieve what was missed, so the flag stays up
            # for the rest of the cycle it happened in — and comes down only
            # here, when a fresh cycle starts with nothing missing from it.
            self.state.cycle_complete = True

    def _refresh_interval(
        self,
        now: datetime,
        ledger: accounting_module.RateLedger,
        has_demand_charge: bool,
        demand_interval: int,
    ) -> None:
        """Advance the demand interval for one ledger.

        Generic over which side it is called for (Gap #4): the import call
        site and the export call site both pass their own ledger and their
        own rate's demand declaration, and the interval arithmetic itself
        does not care which side it is measuring.

        An interval only becomes a peak candidate once it has completed. A
        half-finished one has had less time to accumulate and always reads
        low, so a partial interval at a slot boundary would drag a peak down
        and report a demand charge lower than the bill.
        """
        if not has_demand_charge or not self.counting_allowance:
            return

        key = accounting_module.interval_key(now, demand_interval, self.zone)
        if key is None:
            # Instantaneous. There is no interval to average over, so the
            # reading itself is the candidate and nothing is held open.
            return
        if ledger.interval_key is None:
            ledger.interval_key = key
            return
        if key != ledger.interval_key:
            # The clock has moved past the interval that was open, so it
            # completed. This is the only place a peak can move.
            ledger.close_interval(now, demand_interval)
            ledger.interval_key = key

    def _leave_intervals_except(self, active: set[str]) -> None:
        """Discard part-finished intervals for every ledger not in force.

        Out of force. Whatever a ledger not named in ``active`` had part-way
        through is discarded rather than closed: it is not a completed
        interval and never will be. Import and export are independent flows
        (rule 5) and each has its own entry in ``active`` when it resolves,
        so one side stopping to resolve never clears the other side's
        in-progress interval.
        """
        for name, ledger in self.state.ledgers.items():
            if name not in active:
                ledger.interval_kwh = 0.0
                ledger.interval_key = None

    def _refresh_supply_charge(self, now: datetime, today: date) -> None:
        """Land the declared daily supply charge once, at local midnight.

        Gap #5: the full charge lands the moment the day begins, never
        prorated. The previous design converted elapsed time into a fraction
        of the day (``elapsed / MINUTES_PER_DAY``), which is exactly where a
        23- or 25-hour day bit — a fraction against a fixed 1440-minute
        assumption over- or under-counts on the short or long day. A charge
        that fires once, on the wall clock, at the start of each local
        calendar day has no such fraction to get wrong: it needs to fire
        exactly once per local day, including the short and long ones, and
        firing by comparing today's date against the day it last fired for
        does exactly that.
        """
        daily = self.plan.daily_supply_charge
        if daily <= 0:
            self.state.supply_charge_today = 0.0
            self.state.supply_charge_cycle = 0.0
            self.state.supply_charge_day = today
            return
        if self.state.supply_charge_day != today:
            self.state.supply_charge_today = round(daily, 6)
            self.state.supply_charge_day = today
        # Whole days already landed this cycle, today's included — days_elapsed
        # counts today itself (rule 4: calendar days, not 24-hour spans), and
        # today's charge has already landed in full above.
        self.state.supply_charge_cycle = round(daily * self.state.days_elapsed, 6)

    def _schedule_next_boundary(self) -> None:
        """Wake at whichever comes first, the import change or the feed-in one.

        Compared as real instants. Two datetimes carrying the same tzinfo are
        compared on the wall clock, which picks the wrong one on the day the
        clocks go back.
        """
        if self._boundary_unsubscribe is not None:
            self._boundary_unsubscribe()
            self._boundary_unsubscribe = None
        candidates = [
            moment
            for moment in (self.state.next_change, self.state.next_export_change)
            if moment is not None
        ]
        if not candidates:
            _LOGGER.debug("No further boundary found; nothing scheduled")
            return
        self._boundary_unsubscribe = async_track_point_in_time(
            self.hass,
            self.async_refresh,
            min(candidates, key=lambda moment: moment.astimezone(UTC)),
        )

    # ------------------------------------------------------------- allowances

    def _seed_energy_total(self) -> None:
        if self.counting_allowance:
            entity_id = self.options.get(CONF_IMPORT_ENERGY_SENSOR)
            if entity_id:
                self._last_energy_total = self._read_float(entity_id)
                if self._last_energy_total is None:
                    # The meter was not readable at startup, so the hole
                    # behind the restart cannot be measured and everything
                    # after it under-counts.
                    self._open_gap("the import meter was not readable at startup")
        if self.counting_export_allowance:
            export_entity_id = self.options.get(CONF_EXPORT_ENERGY_SENSOR)
            if export_entity_id:
                self._last_export_energy_total = self._read_float(export_entity_id)
                if self._last_export_energy_total is None:
                    self._open_gap("the export meter was not readable at startup")

    def _read_float(self, entity_id: str) -> float | None:
        state = self.hass.states.get(entity_id)
        if state is None or state.state in UNUSABLE:
            return None
        try:
            return float(state.state)
        except ValueError:
            return None

    @callback
    def _handle_state_change(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        if self.counting_allowance and entity_id == self.options.get(
            CONF_IMPORT_ENERGY_SENSOR
        ):
            self._accumulate_energy(entity_id)
        if self.counting_export_allowance and entity_id == self.options.get(
            CONF_EXPORT_ENERGY_SENSOR
        ):
            self._accumulate_export_energy(entity_id)
        self.async_refresh()

    def _accumulate_energy(self, entity_id: str) -> None:
        """Credit the meter delta to the rate it was drawn under.

        This runs before the refresh, so ``state.resolution`` still names the
        rate that was in force while the energy was being drawn. That is the
        correct place for it, and it is why the credit is made here rather
        than after.

        What was wrong was where it went. A single plan-wide counter meant the
        refresh that followed zeroed the figure the moment the slot changed,
        so consumption in the last moments before a boundary was added to the
        outgoing slot and then thrown away — it always under-counted, so a cap
        was never reported spent early. The ledger below belongs to the rate,
        so the delta stays with the rate that drew it and a different rate
        coming into force touches nothing. That is finding A5.
        """
        reading = self._read_float(entity_id)
        if reading is None:
            if not self._energy_warned:
                _LOGGER.warning(
                    "Import energy sensor %s is unavailable; consumption is not "
                    "being counted and this cycle will under-report",
                    entity_id,
                )
                self._energy_warned = True
            self._open_gap(f"{entity_id} is unavailable, unknown or not a number")
            return
        if self._energy_warned:
            _LOGGER.info("Import energy sensor %s is available again", entity_id)
            self._energy_warned = False
        self._close_gap()

        resolution = self.state.resolution
        if resolution is None:
            # Nothing resolves, so there is no rate to credit. The reading is
            # still recorded, or the whole unresolved stretch would be handed
            # to whichever rate happens to come into force next.
            self._last_energy_total = reading
            return

        rate = resolution.rate
        delta = allowance_module.accumulate(self._last_energy_total, reading, 0.0)
        if delta > 0:
            ledger = self.ledger(resolution.qualified_name)
            if rate.has_allowance:
                ledger.allowance_used_kwh += delta
                self.state.allowance_used_kwh = ledger.allowance_used_kwh
            if rate.has_demand_charge:
                ledger.interval_kwh += delta
        self._last_energy_total = reading

    def _accumulate_export_energy(self, entity_id: str) -> None:
        """Credit the export meter delta to the export rate drawn under.

        The export mirror of ``_accumulate_energy`` (Gap #4). Runs before the
        refresh for the same reason: ``state.export_resolution`` still names
        the export rate in force while the energy was being sent, and
        crediting the delta to the rate it belongs to rather than to
        whichever rate the following refresh finds in force is what finding
        A5 was about on the import side.
        """
        reading = self._read_float(entity_id)
        if reading is None:
            if not self._export_energy_warned:
                _LOGGER.warning(
                    "Export energy sensor %s is unavailable; consumption is not "
                    "being counted and this cycle will under-report",
                    entity_id,
                )
                self._export_energy_warned = True
            self._open_gap(f"{entity_id} is unavailable, unknown or not a number")
            return
        if self._export_energy_warned:
            _LOGGER.info("Export energy sensor %s is available again", entity_id)
            self._export_energy_warned = False
        self._close_gap()

        export_resolution = self.state.export_resolution
        if export_resolution is None or export_resolution.rate_name is None:
            self._last_export_energy_total = reading
            return

        export_rate = export_resolution.day_pattern.export_rate_by_name(
            export_resolution.rate_name
        )
        delta = allowance_module.accumulate(
            self._last_export_energy_total, reading, 0.0
        )
        if delta > 0 and export_rate is not None:
            qname = export_resolution.qualified_name
            assert qname is not None
            ledger = self.ledger(qname)
            if export_rate.has_allowance:
                ledger.allowance_used_kwh += delta
                self.state.export_allowance_used_kwh = ledger.allowance_used_kwh
            if export_rate.has_demand_charge:
                ledger.interval_kwh += delta
        self._last_export_energy_total = reading

    # ------------------------------------------------------------------ gaps

    def _open_gap(self, reason: str) -> None:
        """Record that an input stopped being readable, and raise the repair.

        A Home Assistant repair issue the moment a gap opens, cleared
        automatically when the input returns — the immediate half of section
        6. A gap always makes the figures low: a missed peak never happened as
        far as this component knows, and missed energy was never spent. So the
        flag is not decoration — it is the only thing between an incomplete
        cycle and a confident wrong answer.
        """
        self._gap_reason = reason
        if not self.state.data_complete:
            return
        self.state.data_complete = False
        self.state.gap_since = dt_util.now()
        # Stays up for the rest of the cycle even after the input returns,
        # because recovery does not retrieve what was missed.
        self.state.cycle_complete = False
        for ledger in self.state.ledgers.values():
            ledger.incomplete = True
        async_create_issue(
            self.hass,
            DOMAIN,
            self._gap_issue_id,
            is_fixable=False,
            severity=IssueSeverity.WARNING,
            translation_key="input_data_gap",
            translation_placeholders={
                "title": self.plan.name,
                "reason": reason,
                "since": self.state.gap_since.isoformat(),
            },
        )

    def _close_gap(self) -> None:
        """Record that the input is readable again, and clear the repair.

        The immediate flag comes down and the repair clears. The cycle's flag
        does not: it clears when the cycle rolls, and the cycle closes marked
        incomplete.
        """
        if self.state.data_complete:
            return
        if self.state.gap_since is not None:
            self.state.gap_minutes += round(
                (
                    dt_util.now().astimezone(UTC) - self.state.gap_since.astimezone(UTC)
                ).total_seconds()
                / 60.0,
                3,
            )
        self.state.data_complete = True
        self.state.gap_since = None
        async_delete_issue(self.hass, DOMAIN, self._gap_issue_id)

    @property
    def _gap_issue_id(self) -> str:
        return f"{ISSUE_DATA_GAP}_{self.entry_id}"

    def _open_expired_issue(self) -> None:
        """Raise the repair the moment a plan runs past valid_to unreplaced.

        Gap #6: the architecture treats this as the same truth failure a data
        gap is, and gives it the same immediate treatment — a repair issue
        the moment it happens, not just a flag sitting in diagnostics.
        Archiving is excluded structurally: an archived plan's own valid_to
        was set by the user with a successor in hand, and is_active_on
        already reports it as inactive without this method being told
        which case it is — the case this raises for is specifically the one
        nobody told the service to stop being true, it just ran out.
        """
        if self._expired_warned:
            return
        self._expired_warned = True
        async_create_issue(
            self.hass,
            DOMAIN,
            self._expired_issue_id,
            is_fixable=False,
            severity=IssueSeverity.WARNING,
            translation_key="plan_expired",
            translation_placeholders={
                "title": self.plan.name,
                "valid_to": (
                    self.plan.valid_to.isoformat() if self.plan.valid_to else ""
                ),
            },
        )

    def _close_expired_issue(self) -> None:
        """Clear the repair once the plan is active again."""
        if not self._expired_warned:
            return
        self._expired_warned = False
        async_delete_issue(self.hass, DOMAIN, self._expired_issue_id)

    @property
    def _expired_issue_id(self) -> str:
        return f"{ISSUE_PLAN_EXPIRED}_{self.entry_id}"

    # ------------------------------------------------------- utility  meters

    @callback
    def _async_write_tariff_selects(self) -> None:
        """Set nominated utility_meter tariff selects to the current rate.

        The only write this integration performs, and only to selects the user
        has explicitly nominated.
        """
        selects: list[str] = list(self.options.get(CONF_TARIFF_SELECTS) or [])
        if not selects:
            return
        resolution = self.state.resolution
        effective = self.state.effective_rate
        tariff = (
            None
            if resolution is None or effective is None
            else plan_module.qualified_name(
                self.plan.name, resolution.day_pattern.name, effective.name
            )
        )
        if tariff is None or tariff == self._last_written_tariff:
            return

        for entity_id in selects:
            state = self.hass.states.get(entity_id)
            if state is None:
                _LOGGER.warning("Tariff select %s does not exist", entity_id)
                continue
            options = state.attributes.get("options") or []
            if tariff not in options:
                _LOGGER.warning(
                    "Tariff select %s has no option '%s'; its options are: %s",
                    entity_id,
                    tariff,
                    ", ".join(options) or "none",
                )
                continue
            if state.state == tariff:
                continue
            self.hass.async_create_task(
                self.hass.services.async_call(
                    "select",
                    "select_option",
                    {"entity_id": entity_id, "option": tariff},
                    blocking=False,
                )
            )
        self._last_written_tariff = tariff

    # ------------------------------------------------------------------ views

    def export_resolution_now(self) -> ExportResolution | None:
        """Return the feed-in declaration in force right now, with context.

        The one place this is computed. export_price_now and
        ExportPriceSensor.extra_state_attributes both read it rather than
        resolving separately, so the price and the day pattern or period
        shown alongside it can never disagree about what moment they
        describe.
        """
        now = dt_util.now()
        return self.plan.export_resolve(
            now.date(), now.hour * 60 + now.minute, self.is_holiday(now.date())
        )

    def export_price_now(self) -> float | None:
        """Return the feed-in price in force, in dollars per kWh, or None."""
        resolution = self.export_resolution_now()
        return None if resolution is None else resolution.pricing.price

    def forward_intervals(
        self, hours: int, resolution_minutes: int
    ) -> list[intervals_module.Interval]:
        """Return the forward interval series from now.

        Held between calls. The series is aligned to the resolution grid, so it
        is the same for every moment inside one slot, and the price sensors ask
        for it every time their attributes are read — which is every state
        write, which with an energy meter attached is several times a minute.
        """
        now = dt_util.now()
        today = now.date()
        aligned = (
            (now.hour * 60 + now.minute) // resolution_minutes
        ) * resolution_minutes
        # ``today``/``aligned`` are wall clock, and a wall-clock minute names
        # two real instants an hour apart on the morning the clocks go back.
        # ``now.fold`` tells them apart the same way ``instants_at`` does, so
        # the second pass forces a rebuild instead of being served the first
        # pass's series.
        key = (
            today,
            aligned,
            hours,
            resolution_minutes,
            self.is_holiday(today),
            now.fold,
        )
        if key != self._forward_key:
            self._forward_series = intervals_module.generate(
                self.plan,
                now,
                self.zone,
                self.is_holiday,
                hours=hours,
                resolution_minutes=resolution_minutes,
            )
            self._forward_key = key
        return self._forward_series

    def today_schedule(
        self, resolution_minutes: int
    ) -> list[intervals_module.Interval]:
        """Return today's full local-midnight-to-midnight schedule.

        Unlike ``forward_intervals``, this always starts at local midnight
        today, whatever the current time is — the whole day the daily rate
        card draws, not just what is still ahead. Reuses ``intervals.
        generate()`` anchored to midnight with ``hours=24`` rather than a
        separate walk, so the real-instants DST handling
        (``instants_at``) is inherited, not reimplemented.
        """
        now = dt_util.now()
        midnight = intervals_module.instants_at(
            now.astimezone(self.zone).date(), 0, self.zone
        )[0]
        return intervals_module.generate(
            self.plan,
            midnight,
            self.zone,
            self.is_holiday,
            hours=24,
            resolution_minutes=resolution_minutes,
        )

    @property
    def problems(self) -> list[str]:
        """Return the plan's validation problems as text."""
        return [str(problem) for problem in validate_plan(self.plan)]

    @property
    def device_identifier(self) -> tuple[str, str]:
        """Return the device registry identifier for this channel."""
        return (DOMAIN, self.entry_id)


HolidayCheck = Callable[[date], bool]
