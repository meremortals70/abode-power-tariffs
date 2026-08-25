"""One binary sensor per declared constraint, one per demand-charged rate, and
one for whether every input has been readable this cycle.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TariffConfigEntry
from .const import KEY_DATA_COMPLETE
from .coordinator import TariffCoordinator
from .entity import RateTariffEntity, TariffEntity
from .plan import DayPattern, ExportRate, Rate, format_time

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TariffConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the constraint sensors, the demand sensors and the data flag."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        ConstraintBinarySensor(coordinator, constraint)
        for constraint in coordinator.plan.constraints
    ]
    # One per rate that carries a demand charge, not one per plan. It was one
    # per plan, which could only ever describe whichever rate happened to be
    # in force and had nothing to say about a demand window on any other rate
    # while a different one was active. Its unique id changes with that — the
    # one genuine break in this change, alongside the allowance sensor.
    for day_pattern, rate in coordinator.plan.rates_with_pattern():
        if rate.demand_period:
            entities.append(DemandPeriodBinarySensor(coordinator, day_pattern, rate))
    # The export mirror (Gaps #2, #3): an export rate can now declare a
    # demand charge of its own.
    for day_pattern, export_rate in coordinator.plan.export_rates_with_pattern():
        if export_rate.demand_period:
            entities.append(
                DemandPeriodBinarySensor(
                    coordinator, day_pattern, export_rate, export=True
                )
            )
    if coordinator.accounts:
        entities.append(DataCompleteBinarySensor(coordinator))
    async_add_entities(entities)


class ConstraintBinarySensor(TariffEntity, BinarySensorEntity):
    """On while a rate carrying this constraint is in force."""

    def __init__(self, coordinator: TariffCoordinator, constraint: str) -> None:
        """Initialise the constraint sensor."""
        super().__init__(coordinator, f"constraint_{_slug(constraint)}")
        self._constraint = constraint
        # Constraints are user-named, so there is no translation for them.
        self._attr_translation_key = None
        self._attr_name = constraint.replace("_", " ").capitalize()

    @property
    def is_on(self) -> bool:
        """Return whether the constraint applies right now."""
        rate = self.coordinator.state.effective_rate
        return rate is not None and self._constraint in rate.constraints

    @property
    def enforceable(self) -> bool:
        """Return whether the rate in force declares this rule enforceable.

        A declaration about what the rate means, not an instruction. Whether
        anything acts on it is the consuming system's decision.
        """
        rate = self.coordinator.state.effective_rate
        return rate is not None and self._constraint in rate.enforceable_constraints

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the period this constraint is currently attached to."""
        resolution = self.coordinator.state.resolution
        if resolution is None or not self.is_on:
            return {"constraint": self._constraint, "enforceable": self.enforceable}
        return {
            "constraint": self._constraint,
            "enforceable": self.enforceable,
            "rate": resolution.qualified_name,
            "period_start": format_time(resolution.period.start),
            "period_end": format_time(resolution.period.end),
        }


def _slug(value: str) -> str:
    """Return a value safe to use in a unique id."""
    return "".join(
        character if character.isalnum() else "_" for character in value.lower()
    )


class DemandPeriodBinarySensor(RateTariffEntity, BinarySensorEntity):
    """On while this rate is in force and carries a demand charge.

    A declaration, the same as the rate's own demand_period field — what an
    automation actually hooks into, rather than reading the interval and
    reimplementing 'is this rate in force right now' itself.
    """

    def __init__(
        self,
        coordinator: TariffCoordinator,
        day_pattern: DayPattern,
        rate: Rate | ExportRate,
        *,
        export: bool = False,
    ) -> None:
        """Initialise the demand period sensor for one rate."""
        super().__init__(
            coordinator, "demand_period_active", day_pattern, rate, export=export
        )

    @property
    def is_on(self) -> bool:
        """Return whether this rate is the one in force right now."""
        return self.in_force

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return this rate's declared demand charge and how it is measured."""
        rate = self.rate
        if rate is None:
            return {"demand_rate_per_kw_month": None}
        return {
            "demand_rate_per_kw_month": rate.demand_rate_per_kw_month,
            "demand_interval": rate.demand_interval,
            "demand_basis": rate.demand_basis,
        }


class DataCompleteBinarySensor(TariffEntity, BinarySensorEntity):
    """Off the moment an input becomes unreadable; the red flag for the cycle.

    Two distinct facts share this entity. The state is the immediate one — an
    input is unreadable right now — and it clears the moment the input comes
    back. Whether the *cycle* is unaffected is a separate, longer-lived fact:
    it stays down until the cycle rolls, because recovery does not retrieve
    what was missed. Both are published, because a consumer deciding whether
    to trust a peak or an allowance figure needs to know which one it is
    asking about.
    """

    _attr_device_class = "problem"

    def __init__(self, coordinator: TariffCoordinator) -> None:
        """Initialise the data-complete sensor."""
        super().__init__(coordinator, KEY_DATA_COMPLETE)

    @property
    def is_on(self) -> bool:
        """On means there is a problem — an input is unreadable right now."""
        return not self.coordinator.state.data_complete

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the cycle flag and what is known about the gap."""
        state = self.coordinator.state
        return {
            # The persistent flag. Off means the whole cycle so far is
            # unaffected; it does not come back on for a gap that has closed.
            "cycle_complete": state.cycle_complete,
            "gap_since": state.gap_since.isoformat() if state.gap_since else None,
            "gap_minutes_this_cycle": round(state.gap_minutes, 1),
        }

    @property
    def available(self) -> bool:
        """The flag is meaningful whether or not a period currently resolves."""
        return True
