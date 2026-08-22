"""Sensors for Abode Power Tariffs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TariffConfigEntry
from . import accounting as accounting_module
from .const import (
    ATTR_ALLOWANCE_SLOT,
    ATTR_CYCLE_COMPLETE,
    ATTR_CYCLE_END,
    ATTR_CYCLE_START,
    ATTR_ESTIMATE,
    ATTR_QUALIFIED_RATE,
    DEFAULT_HOURS,
    DEFAULT_RESOLUTION_MINUTES,
    KEY_ALLOWANCE_REMAINING,
    KEY_ALLOWANCE_USED,
    KEY_BILLING_CYCLE_PROGRESS,
    KEY_DEMAND_COST_PROJECTED,
    KEY_DEMAND_COST_TO_DATE,
    KEY_DEMAND_NOW_KW,
    KEY_DEMAND_PEAK_AT,
    KEY_DEMAND_PEAK_KW,
    KEY_SUPPLY_CHARGE_ENERGY,
    KEY_SUPPLY_CHARGE_TODAY,
)
from .coordinator import TariffCoordinator
from .entity import RateTariffEntity, TariffEntity
from .plan import Rate, format_time

# Said on every accumulating entity. What this component publishes from
# counting is an estimate it measured itself: it is taken from a meter the
# user nominated, on a clock this component keeps, and it will not reconcile
# with a retailer's bill.
ESTIMATE_NOTE = (
    "An estimate measured by this integration. It will not reconcile with a bill."
)

# Nothing is polled and nothing is written on update, so there is no reason to
# serialise entity work.
PARALLEL_UPDATES = 0

# The Energy dashboard matches a price entity by its unit, which must be the
# configured currency over kWh. There is no device class for a unit price.
ENERGY_PRICE_SUFFIX = "/kWh"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TariffConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors for one tariff channel."""
    coordinator = entry.runtime_data
    currency = hass.config.currency

    entities: list[SensorEntity] = [
        ImportPriceSensor(coordinator, currency),
        ExportPriceSensor(coordinator, currency),
        RateSensor(coordinator),
        NextRateChangeSensor(coordinator),
        SupplyChargeSensor(coordinator, currency),
    ]

    # Only when the feed-in price actually moves. A plan on one export price
    # all day would get an entity that never has anything to say.
    if coordinator.plan.has_export_periods:
        entities.append(NextExportChangeSensor(coordinator))

    # Fixed charges accumulate (rule 11, revoked and reinstated). These two
    # keep the unique ids the sensors removed at P11 had, so the entities
    # lingering unavailable in a registry are reclaimed rather than needing
    # deletion by hand.
    if coordinator.plan.daily_supply_charge > 0:
        entities.append(SupplyChargeTodaySensor(coordinator, currency))
        entities.append(SupplyChargeCycleSensor(coordinator, currency))

    if coordinator.accounts:
        entities.append(BillingCycleProgressSensor(coordinator))

    # One set per rate, keyed on the qualified identifier. A plan with two
    # timetables of three rates each, all carrying both declarations,
    # publishes a lot of entities — that is the cost of per-rate accounting
    # and it is stated in the proposal rather than discovered here. The lever
    # if it is too many is entity_registry_enabled_default on the derived
    # ones, not fewer facts.
    if coordinator.counting_allowance:
        for rate in coordinator.plan.rates:
            if rate.has_allowance:
                entities.append(AllowanceUsedSensor(coordinator, rate))
                entities.append(AllowanceRemainingSensor(coordinator, rate))
            if rate.has_demand_charge:
                entities.append(DemandNowSensor(coordinator, rate))
                entities.append(DemandPeakSensor(coordinator, rate))
                entities.append(DemandPeakAtSensor(coordinator, rate))
                entities.append(DemandCostToDateSensor(coordinator, rate, currency))
                entities.append(DemandCostProjectedSensor(coordinator, rate, currency))

    async_add_entities(entities)


class _PriceSensor(TariffEntity, SensorEntity):
    """Common behaviour for the two price sensors."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 4

    # The forecast is a 24-hour prediction, roughly 4 KB of it, rebuilt on the
    # half hour. Keeping a history of predictions has no value and writing one
    # every time the entity updates is measured in tens of megabytes a day.
    _unrecorded_attributes = frozenset({"forecast"})

    def __init__(self, coordinator: TariffCoordinator, key: str, currency: str) -> None:
        """Initialise a price sensor with the configured currency."""
        super().__init__(coordinator, key)
        self._attr_native_unit_of_measurement = f"{currency}{ENERGY_PRICE_SUFFIX}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the period, the rules in force, and the forward series."""
        state = self.coordinator.state
        resolution = state.resolution
        rate = state.effective_rate

        attributes: dict[str, Any] = {
            "rate": rate.qualified_name if rate else None,
            "rate_name": rate.name if rate else None,
            "day_pattern": resolution.day_pattern.name if resolution else None,
            "season": (
                resolution.day_pattern.name
                if resolution and resolution.day_pattern.is_seasonal
                else None
            ),
            "period_start": format_time(resolution.period.start)
            if resolution
            else None,
            "period_end": format_time(resolution.period.end) if resolution else None,
            "constraints": sorted(rate.constraints) if rate else [],
            "enforceable_constraints": (
                sorted(rate.enforceable_constraints) if rate else []
            ),
            "coasting_permitted": rate.coasting_permitted if rate else None,
            "allowance_exhausted": state.allowance_exhausted,
            # Says plainly whether this price accounts for a cap being spent.
            "allowance_counted": self.coordinator.counting_allowance,
            "plan_expired": state.plan_expired,
            "trace": list(state.trace),
        }

        # evcc reads a list of {start, end, value} from a named attribute.
        series = self.coordinator.forward_intervals(
            DEFAULT_HOURS, DEFAULT_RESOLUTION_MINUTES
        )
        attributes["forecast"] = [interval.as_evcc_entry() for interval in series]
        return attributes


class ImportPriceSensor(_PriceSensor):
    """The price of imported energy right now."""

    def __init__(self, coordinator: TariffCoordinator, currency: str) -> None:
        """Initialise the import price sensor."""
        super().__init__(coordinator, "import_price", currency)

    @property
    def native_value(self) -> float | None:
        """Return dollars per kWh."""
        rate = self.coordinator.state.effective_rate
        return None if rate is None else round(rate.import_price, 6)


class ExportPriceSensor(_PriceSensor):
    """The price paid for exported energy right now."""

    def __init__(self, coordinator: TariffCoordinator, currency: str) -> None:
        """Initialise the export price sensor."""
        super().__init__(coordinator, "export_price", currency)

    @property
    def native_value(self) -> float | None:
        """Return dollars per kWh."""
        return round(self.coordinator.export_price_now(), 6)

    @property
    def available(self) -> bool:
        """A flat export price does not depend on an import period resolving."""
        return True


class RateSensor(TariffEntity, SensorEntity):
    """The name of the rate in force."""

    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(self, coordinator: TariffCoordinator) -> None:
        """Initialise the rate sensor with the plan's rate names as options."""
        super().__init__(coordinator, "rate")
        self._attr_options = list(coordinator.plan.qualified_rate_names)

    @property
    def native_value(self) -> str | None:
        """Return the rate name."""
        rate = self.coordinator.state.effective_rate
        return None if rate is None else rate.qualified_name

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the scheduled rate, which differs when an allowance is spent."""
        resolution = self.coordinator.state.resolution
        return {
            "scheduled_rate": (resolution.rate.qualified_name if resolution else None),
            "rate_name": resolution.rate.name if resolution else None,
            "timetable": resolution.rate.timetable if resolution else None,
            "allowance_exhausted": self.coordinator.state.allowance_exhausted,
        }


class NextRateChangeSensor(TariffEntity, SensorEntity):
    """When the rate next changes."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: TariffCoordinator) -> None:
        """Initialise the next rate change sensor."""
        super().__init__(coordinator, "next_rate_change")

    @property
    def native_value(self) -> datetime | None:
        """Return the next boundary."""
        return self.coordinator.state.next_change


class NextExportChangeSensor(TariffEntity, SensorEntity):
    """When the feed-in price next changes.

    Separate from the rate change, because they are separate facts. A battery
    weighing a good export now against a cheaper import later needs both, and
    an automation should be able to trigger on either without the other.
    """

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: TariffCoordinator) -> None:
        """Initialise the next feed-in change sensor."""
        super().__init__(coordinator, "next_export_change")

    @property
    def native_value(self) -> datetime | None:
        """Return the next feed-in boundary."""
        return self.coordinator.state.next_export_change

    @property
    def available(self) -> bool:
        """The feed-in schedule does not depend on an import period resolving."""
        return True


class SupplyChargeSensor(TariffEntity, SensorEntity):
    """The daily supply charge, as configured."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 4

    def __init__(self, coordinator: TariffCoordinator, currency: str) -> None:
        """Initialise the daily supply charge sensor."""
        super().__init__(coordinator, "daily_supply_charge")
        self._attr_native_unit_of_measurement = f"{currency}/d"

    @property
    def native_value(self) -> float:
        """Return dollars per day."""
        return round(self.coordinator.plan.daily_supply_charge, 6)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the fixed charges the plan declares.

        The declared figures, published as entered. What they have accrued to
        is a different question and is answered by its own sensors — rule 11
        was revoked, so the cycle is computed rather than left to a consumer.
        """
        plan = self.coordinator.plan
        state = self.coordinator.state
        return {
            "monthly_charge": round(plan.monthly_charge, 6),
            "billing_cycle_day": plan.billing_cycle_day,
            ATTR_CYCLE_START: (
                state.cycle_start.isoformat() if state.cycle_start else None
            ),
            ATTR_CYCLE_END: state.cycle_end.isoformat() if state.cycle_end else None,
        }

    @property
    def available(self) -> bool:
        """The supply charge does not depend on a period resolving."""
        return True


class _AccumulatingSensor(RateTariffEntity, RestoreSensor):
    """Common behaviour for the per-rate accumulating sensors."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Say which rate this is, and that the figure is an estimate."""
        state = self.coordinator.state
        return {
            ATTR_QUALIFIED_RATE: self._qualified_name,
            ATTR_ESTIMATE: ESTIMATE_NOTE,
            ATTR_CYCLE_START: (
                state.cycle_start.isoformat() if state.cycle_start else None
            ),
            ATTR_CYCLE_END: state.cycle_end.isoformat() if state.cycle_end else None,
            # A gap always makes the figure low, so anything reading this
            # needs to know the cycle had one.
            ATTR_CYCLE_COMPLETE: state.cycle_complete,
        }


class AllowanceUsedSensor(_AccumulatingSensor):
    """How much of this rate's allowance has been spent in the current period.

    Which period that is was declared: each occurrence of the rate's slot, or
    the whole billing cycle.
    """

    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY_STORAGE
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: TariffCoordinator, rate: Rate) -> None:
        """Initialise the allowance used sensor for one rate."""
        super().__init__(coordinator, KEY_ALLOWANCE_USED, rate)

    async def async_added_to_hass(self) -> None:
        """Restore the count, but only if it belongs to the period running now."""
        await super().async_added_to_hass()
        ledger = self.coordinator.ledger_for(self._qualified_name)
        if ledger is None:
            return
        restored = await self._restored_value()
        if restored is None:
            return
        value, period = restored
        if period is None or period != ledger.allowance_key:
            # A different slot occurrence, or a different billing cycle. The
            # figure belonged to that one and says nothing about this.
            return
        ledger.allowance_used_kwh = value

    async def _restored_value(self) -> tuple[float, str | None] | None:
        last = await self.async_get_last_sensor_data()
        if last is None or last.native_value is None:
            return None
        try:
            value = float(last.native_value)
        except (TypeError, ValueError):
            return None
        period = None
        if (state := await self.async_get_last_state()) is not None:
            period = state.attributes.get(ATTR_ALLOWANCE_SLOT)
        return value, period

    @property
    def native_value(self) -> float | None:
        """Return kWh spent in the current period."""
        ledger = self.ledger
        return None if ledger is None else round(ledger.allowance_used_kwh, 6)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Publish the period the count belongs to, so a restore can check it."""
        attributes = super().extra_state_attributes
        ledger = self.ledger
        rate = self.rate
        attributes[ATTR_ALLOWANCE_SLOT] = (
            None if ledger is None else ledger.allowance_key
        )
        attributes["allowance_period"] = None if rate is None else rate.allowance_period
        attributes["allowance_kwh"] = None if rate is None else rate.rate_allowance_kwh
        return attributes


class AllowanceRemainingSensor(_AccumulatingSensor):
    """How much of this rate's allowance is left.

    One per rate. It was one per plan, which could only ever describe whichever
    rate happened to be in force and had nothing to say about a cap on any
    other. Its unique id changes with that, which is the one genuine break in
    this change.
    """

    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY_STORAGE
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: TariffCoordinator, rate: Rate) -> None:
        """Initialise the allowance remaining sensor for one rate."""
        super().__init__(coordinator, KEY_ALLOWANCE_REMAINING, rate)

    @property
    def native_value(self) -> float | None:
        """Return kWh remaining."""
        rate = self.rate
        ledger = self.ledger
        if rate is None or rate.rate_allowance_kwh is None:
            return None
        used = 0.0 if ledger is None else ledger.allowance_used_kwh
        return round(max(0.0, rate.rate_allowance_kwh - used), 6)


class DemandNowSensor(_AccumulatingSensor):
    """The average draw over the demand interval in progress."""

    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_suggested_display_precision = 3

    def __init__(self, coordinator: TariffCoordinator, rate: Rate) -> None:
        """Initialise the demand-in-progress sensor for one rate."""
        super().__init__(coordinator, KEY_DEMAND_NOW_KW, rate)

    @property
    def native_value(self) -> float | None:
        """Return kW so far this interval.

        Reads low until the interval completes, which is exactly why a partial
        interval is never a peak candidate.
        """
        rate = self.rate
        ledger = self.ledger
        if rate is None or ledger is None:
            return None
        return accounting_module.average_kw(ledger.interval_kwh, rate.demand_interval)


class DemandPeakSensor(_AccumulatingSensor):
    """The highest completed interval this billing cycle.

    The number the bill is built on. The retailer tells you what it was after
    the cycle closes, by which time the half hour that set it is a month gone.
    """

    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_suggested_display_precision = 3

    def __init__(self, coordinator: TariffCoordinator, rate: Rate) -> None:
        """Initialise the demand peak sensor for one rate."""
        super().__init__(coordinator, KEY_DEMAND_PEAK_KW, rate)

    async def async_added_to_hass(self) -> None:
        """Restore the peak, but only if it was set inside this cycle."""
        await super().async_added_to_hass()
        ledger = self.coordinator.ledger_for(self._qualified_name)
        if ledger is None:
            return
        last = await self.async_get_last_sensor_data()
        if last is None or last.native_value is None:
            return
        cycle = None
        if (state := await self.async_get_last_state()) is not None:
            cycle = state.attributes.get(ATTR_CYCLE_START)
        current = (
            self.coordinator.state.cycle_start.isoformat()
            if self.coordinator.state.cycle_start
            else None
        )
        if cycle is None or cycle != current:
            # A peak from a cycle the retailer has already billed. It is not
            # this cycle's number and restoring it would invent a charge.
            return
        try:
            ledger.peak_kw = float(last.native_value)
        except (TypeError, ValueError):
            return

    @property
    def native_value(self) -> float | None:
        """Return the peak in kW."""
        ledger = self.ledger
        return None if ledger is None else round(ledger.peak_kw, 6)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the declared measurement basis alongside the figure."""
        attributes = super().extra_state_attributes
        rate = self.rate
        if rate is not None:
            attributes["demand_interval"] = rate.demand_interval
            attributes["demand_basis"] = rate.demand_basis
        return attributes


class DemandPeakAtSensor(RateTariffEntity, SensorEntity):
    """When this cycle's peak was set. Which half hour did it."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: TariffCoordinator, rate: Rate) -> None:
        """Initialise the peak timestamp sensor for one rate."""
        super().__init__(coordinator, KEY_DEMAND_PEAK_AT, rate)

    @property
    def native_value(self) -> datetime | None:
        """Return when the peak was set."""
        ledger = self.ledger
        return None if ledger is None else ledger.peak_at


class _DemandCostSensor(_AccumulatingSensor):
    """Common behaviour for the two demand cost sensors."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_suggested_display_precision = 2

    def __init__(
        self, coordinator: TariffCoordinator, rate: Rate, key: str, currency: str
    ) -> None:
        """Initialise a demand cost sensor for one rate."""
        super().__init__(coordinator, key, rate)
        self._attr_native_unit_of_measurement = currency

    def _cost(self, days: int) -> float | None:
        rate = self.rate
        ledger = self.ledger
        if rate is None or ledger is None:
            return None
        return accounting_module.demand_cost(
            ledger.peak_kw, rate.demand_rate_per_kw_month, rate.demand_basis, days
        )


class DemandCostToDateSensor(_DemandCostSensor):
    """What the peak has cost so far, on the declared basis."""

    def __init__(
        self, coordinator: TariffCoordinator, rate: Rate, currency: str
    ) -> None:
        """Initialise the cost-to-date sensor for one rate."""
        super().__init__(coordinator, rate, KEY_DEMAND_COST_TO_DATE, currency)

    @property
    def native_value(self) -> float | None:
        """Return the cost over the days elapsed."""
        return self._cost(self.coordinator.state.days_elapsed)


class DemandCostProjectedSensor(_DemandCostSensor):
    """What the bill says if nothing beats the peak."""

    def __init__(
        self, coordinator: TariffCoordinator, rate: Rate, currency: str
    ) -> None:
        """Initialise the projected cost sensor for one rate."""
        super().__init__(coordinator, rate, KEY_DEMAND_COST_PROJECTED, currency)

    @property
    def native_value(self) -> float | None:
        """Return the cost over the whole cycle."""
        return self._cost(self.coordinator.state.days_in_cycle)


class _SupplyChargeAccrualSensor(TariffEntity, RestoreSensor):
    """Common behaviour for the two accrued supply charge sensors."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: TariffCoordinator, key: str, currency: str) -> None:
        """Initialise an accrued supply charge sensor."""
        super().__init__(coordinator, key)
        self._attr_native_unit_of_measurement = currency

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the cycle this accrual belongs to."""
        state = self.coordinator.state
        plan = self.coordinator.plan
        return {
            ATTR_ESTIMATE: ESTIMATE_NOTE,
            ATTR_CYCLE_START: (
                state.cycle_start.isoformat() if state.cycle_start else None
            ),
            ATTR_CYCLE_END: state.cycle_end.isoformat() if state.cycle_end else None,
            ATTR_CYCLE_COMPLETE: state.cycle_complete,
            "daily_supply_charge": round(plan.daily_supply_charge, 6),
            "monthly_charge": round(plan.monthly_charge, 6),
        }

    @property
    def available(self) -> bool:
        """A fixed charge accrues whether or not a period resolves."""
        return True


class SupplyChargeTodaySensor(_SupplyChargeAccrualSensor):
    """The daily supply charge accrued so far today.

    Reinstated with rule 11. Accrued across the real length of the day, so the
    23-hour day accrues the whole daily charge and no more and the 25-hour day
    does not accrue an extra hour of it.
    """

    def __init__(self, coordinator: TariffCoordinator, currency: str) -> None:
        """Initialise the supply charge accrued today."""
        super().__init__(coordinator, KEY_SUPPLY_CHARGE_TODAY, currency)

    @property
    def native_value(self) -> float:
        """Return dollars accrued today."""
        return self.coordinator.state.supply_charge_today


class SupplyChargeCycleSensor(_SupplyChargeAccrualSensor):
    """The supply charge accrued so far this billing cycle.

    Whole days already closed plus today's part. The monthly charge is a
    separate declared figure and is published as an attribute rather than
    folded in, because the two are billed as two lines.
    """

    def __init__(self, coordinator: TariffCoordinator, currency: str) -> None:
        """Initialise the supply charge accrued this cycle."""
        super().__init__(coordinator, KEY_SUPPLY_CHARGE_ENERGY, currency)

    @property
    def native_value(self) -> float:
        """Return dollars accrued this cycle."""
        return self.coordinator.state.supply_charge_cycle


class BillingCycleProgressSensor(TariffEntity, SensorEntity):
    """How far through the billing cycle this is.

    Days elapsed of the days in the cycle. Calendar days, because rule 4 says
    a day is 23, 24 or 25 hours and the month containing a transition has the
    same number of days it always did.
    """

    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: TariffCoordinator) -> None:
        """Initialise the billing cycle progress sensor."""
        super().__init__(coordinator, KEY_BILLING_CYCLE_PROGRESS)

    @property
    def native_value(self) -> float | None:
        """Return how much of the cycle has elapsed, as a percentage."""
        state = self.coordinator.state
        if not state.days_in_cycle:
            return None
        return round(100.0 * state.days_elapsed / state.days_in_cycle, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the cycle's dates and how much of it is left."""
        state = self.coordinator.state
        return {
            ATTR_CYCLE_START: (
                state.cycle_start.isoformat() if state.cycle_start else None
            ),
            ATTR_CYCLE_END: state.cycle_end.isoformat() if state.cycle_end else None,
            "days_elapsed": state.days_elapsed,
            "days_in_cycle": state.days_in_cycle,
            "days_remaining": max(0, state.days_in_cycle - state.days_elapsed),
            "billing_cycle_day": self.coordinator.plan.billing_cycle_day,
            ATTR_CYCLE_COMPLETE: state.cycle_complete,
        }

    @property
    def available(self) -> bool:
        """The cycle runs whether or not a period resolves."""
        return True
