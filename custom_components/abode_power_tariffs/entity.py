"""Base entity for Abode Power Tariffs."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .accounting import RateLedger
from .const import DOMAIN, SIGNAL_UPDATE
from .coordinator import TariffCoordinator
from .plan import DayPattern, ExportRate, Rate
from .plan import qualified_name as build_qualified_name


class TariffEntity(Entity):
    """An entity backed by one tariff channel."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: TariffCoordinator,
        key: str,
        qualified_name: str | None = None,
    ) -> None:
        """Initialise the entity.

        ``qualified_name`` makes this one of a set, one per rate. A rate is its
        timetable plus its name (rule 10), so the identifier is what goes in
        the unique id — never the bare name, which two timetables can share.
        Without it the entity is one per plan, as before.
        """
        self.coordinator = coordinator
        self._key = key
        self._qualified_name = qualified_name
        if qualified_name is None:
            self._attr_unique_id = f"{coordinator.entry_id}_{key}"
        else:
            self._attr_unique_id = f"{coordinator.entry_id}_{qualified_name}_{key}"
        self._attr_translation_key = key
        if qualified_name is not None:
            # The identifier is what a human is shown alongside the rate
            # anywhere uniqueness matters, so it goes in the name too.
            self._attr_translation_placeholders = {"rate": qualified_name}
        self._attr_device_info = DeviceInfo(
            identifiers={coordinator.device_identifier},
            entry_type=DeviceEntryType.SERVICE,
            manufacturer="Abode",
            name=coordinator.plan.name,
            model="Tariff plan",
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe once the entity is registered and can write state."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_UPDATE}_{self.coordinator.entry_id}",
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        """Write the new state after the coordinator recomputed."""
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return whether the plan resolves at this moment.

        An expired plan is still available: it holds its last known prices and
        raises a repair issue, because removing the price entity would stop
        Energy dashboard cost tracking without saying so.
        """
        return self.coordinator.state.resolution is not None


class RateTariffEntity(TariffEntity):
    """An entity belonging to one rate rather than to the plan.

    One set per ``plan.timetable.import.peak`` (or ``...export.peak``), never
    one per ``peak``. Two timetables can each carry a rate called Peak at
    different prices with different demand charges, and an import rate can
    share a name with an export rate on the very same timetable — anything
    keyed on the bare name collapses them together, which has already
    happened once, in strip.py, and turned two timetables into one colour.
    """

    def __init__(
        self,
        coordinator: TariffCoordinator,
        key: str,
        day_pattern: DayPattern,
        rate: Rate | ExportRate,
        *,
        export: bool = False,
    ) -> None:
        """Initialise an entity scoped to one rate, on one side of one timetable."""
        identifier = build_qualified_name(
            coordinator.plan.name, day_pattern.name, rate.name, export=export
        )
        super().__init__(coordinator, key, qualified_name=identifier)
        self._rate_name = rate.name
        self._timetable = day_pattern.name
        self._export = export

    @property
    def rate(self) -> Rate | ExportRate | None:
        """Return this entity's rate as the plan currently holds it.

        Looked up rather than held, so a price edited in Configure is picked
        up. The entry is reloaded on an options change, but the lookup costs
        nothing and makes the entity independent of that happening.
        """
        assert self._qualified_name is not None
        pattern = self.coordinator.plan.day_pattern_by_name(self._timetable)
        if pattern is None:
            return None
        if self._export:
            return pattern.export_rate_by_name(self._rate_name)
        return pattern.rate_by_name(self._rate_name)

    @property
    def ledger(self) -> RateLedger | None:
        """Return this rate's ledger, or None before anything accumulated."""
        assert self._qualified_name is not None
        return self.coordinator.state.ledgers.get(self._qualified_name)

    @property
    def in_force(self) -> bool:
        """Return whether this rate is the one in force right now."""
        if self._export:
            resolution = self.coordinator.state.export_resolution
            return (
                resolution is not None
                and resolution.qualified_name == self._qualified_name
            )
        resolution = self.coordinator.state.resolution
        return (
            resolution is not None and resolution.qualified_name == self._qualified_name
        )

    @property
    def available(self) -> bool:
        """Return True whatever is in force.

        An accumulated figure is a fact about the whole cycle, not about this
        minute. A peak set on Tuesday is still the number the bill is built on
        at midnight on Sunday, so the entity that reports it cannot go
        unavailable the moment its rate stops being in force.
        """
        return self.rate is not None


DEVICE_DOMAIN = DOMAIN
