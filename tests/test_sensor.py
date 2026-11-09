"""Tests for the sensor platform.

Drives the sensor module through its own setup entry and individual sensor
properties, using the same thin stubs as the other platform tests.
"""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _ha_stubs

_ha_stubs.install()

PACKAGE = "abode_power_tariffs_sensor"
ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "abode_power_tariffs"
ORDER = (
    "const",
    "plan",
    "validate",
    "intervals",
    "allowance",
    "strip",
    "serialise",
    "coordinator",
    "entity",
    "__init__",
    "sensor",
)


def _load() -> types.ModuleType:
    if PACKAGE in sys.modules:
        return sys.modules[PACKAGE]
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(ROOT)]
    sys.modules[PACKAGE] = package
    for name in ORDER:
        target = PACKAGE if name == "__init__" else f"{PACKAGE}.{name}"
        spec = importlib.util.spec_from_file_location(target, ROOT / f"{name}.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        if name == "__init__":
            module.__path__ = [str(ROOT)]
            module.__package__ = PACKAGE
        sys.modules[target] = module
        spec.loader.exec_module(module)
        if name != "__init__":
            setattr(package, name, module)
    return sys.modules[PACKAGE]


PKG = _load()
CONST = sys.modules[f"{PACKAGE}.const"]
Plan = sys.modules[f"{PACKAGE}.plan"].Plan
TariffCoordinator = sys.modules[f"{PACKAGE}.coordinator"].TariffCoordinator
sensor = sys.modules[f"{PACKAGE}.sensor"]
BRISBANE = ZoneInfo("Australia/Brisbane")


def at(hour: int, minute: int = 0, day: int = 14) -> datetime:
    return datetime(2026, 8, day, hour, minute, tzinfo=BRISBANE)


def sample_options() -> dict[str, Any]:
    return {
        CONST.CONF_DAY_PATTERNS: [
            {
                CONST.CONF_NAME: "Every day",
                CONST.CONF_DAYS: list(CONST.ALL_DAY_TOKENS),
                CONST.CONF_RATES: [
                    {
                        CONST.CONF_NAME: "Off Peak",
                        CONST.CONF_IMPORT_CENTS: 19.8,
                        CONST.CONF_CONSTRAINTS: ["grid_charge_battery"],
                    },
                    {
                        CONST.CONF_NAME: "Peak",
                        CONST.CONF_IMPORT_CENTS: 56.88,
                        CONST.CONF_CONSTRAINTS: ["no_grid_import"],
                        CONST.CONF_DEMAND_PERIOD: True,
                        CONST.CONF_DEMAND_RATE: 20.0,
                        CONST.CONF_DEMAND_INTERVAL: 30,
                    },
                ],
                CONST.CONF_PERIODS: [
                    {
                        CONST.CONF_START: "00:00",
                        CONST.CONF_END: "16:00",
                        CONST.CONF_RATE: "Off Peak",
                    },
                    {
                        CONST.CONF_START: "16:00",
                        CONST.CONF_END: "24:00",
                        CONST.CONF_RATE: "Peak",
                    },
                ],
                CONST.CONF_EXPORT_SAME_ALL_DAY: False,
                CONST.CONF_EXPORT_PERIODS: [
                    {CONST.CONF_START: "00:00", CONST.CONF_END: "24:00", CONST.CONF_RATE: "Day"},
                ],
                CONST.CONF_EXPORT_RATES: [
                    {
                        CONST.CONF_NAME: "Day",
                        CONST.CONF_EXPORT_CENTS: 5.0,
                        CONST.CONF_EXPORT_ALLOWANCE_KWH: 10.0,
                        CONST.CONF_DEMAND_PERIOD: True,
                        CONST.CONF_DEMAND_RATE: 15.0,
                        CONST.CONF_DEMAND_INTERVAL: 30,
                    }
                ],
            }
        ],
        CONST.CONF_SUPPLY_CHARGE_CENTS: 116.6,
        CONST.CONF_PRICES_INCLUDE_GST: True,
        CONST.CONF_GST_PERCENT: 10.0,
    }


def a_coordinator(options: dict[str, Any] | None = None) -> Any:
    hass = _ha_stubs.FakeHass()
    data = options or sample_options()
    plan = Plan.from_dict({**data, CONST.CONF_NAME: "Test"})
    return TariffCoordinator(hass, "entry1", plan, data)


class SensorCase(unittest.TestCase):
    def setUp(self) -> None:
        _ha_stubs.SCHEDULED.__init__()  # type: ignore[misc]
        sys.modules[f"{PACKAGE}.coordinator"].dt_util.NOW = at(10)
        sensor_mod = sys.modules["homeassistant.components.sensor"]
        sensor_mod.RestoreSensor.RESTORED = None
        sensor_mod.RestoreSensor.RESTORED_STATE = None

    def tearDown(self) -> None:
        sys.modules[f"{PACKAGE}.coordinator"].dt_util.NOW = None


class TestAsyncSetupEntry(SensorCase):
    def setUp(self) -> None:
        super().setUp()
        self.added: list[Any] = []

    def _add(self, entities: Any) -> None:
        self.added.extend(entities)

    def test_zero_supply_charge_skips_accrual_sensors(self) -> None:
        """Line 91->95: daily_supply_charge <= 0."""
        options = sample_options()
        options[CONST.CONF_SUPPLY_CHARGE_CENTS] = 0.0
        coordinator = a_coordinator(options)
        run_setup(coordinator, self._add)
        keys = {e._attr_unique_id for e in self.added}
        self.assertNotIn("entry1_supply_charge_today", keys)
        self.assertNotIn("entry1_supply_charge_energy", keys)

    def test_export_declarations_create_export_sensors(self) -> None:
        """Lines 126-155: export allowance and demand sensors."""
        options = sample_options()
        options[CONST.CONF_IMPORT_ENERGY_SENSOR] = "sensor.grid_import"
        options[CONST.CONF_EXPORT_ENERGY_SENSOR] = "sensor.grid_export"
        coordinator = a_coordinator(options)
        run_setup(coordinator, self._add)
        keys = {e._attr_unique_id for e in self.added}
        self.assertIn(
            "entry1_test.every_day.export.day_allowance_used_kwh", keys
        )
        self.assertIn(
            "entry1_test.every_day.export.day_demand_peak_kw", keys
        )


def run_setup(coordinator: Any, add: Any) -> None:
    import asyncio

    class Entry:
        runtime_data = coordinator

    asyncio.run(sensor.async_setup_entry(coordinator.hass, Entry(), add))


class TestRateSensor(SensorCase):
    def test_native_value_none_when_no_resolution(self) -> None:
        """Line 347."""
        coordinator = a_coordinator()
        coordinator.state.resolution = None
        coordinator.state.effective_rate = None
        entity = sensor.RateSensor(coordinator)
        self.assertIsNone(entity.native_value)


class TestDemandNowSensor(SensorCase):
    def test_native_value_none_without_rate(self) -> None:
        """Line 643."""
        coordinator = a_coordinator()
        day_pattern = coordinator.plan.day_pattern_by_name("Every day")
        rate = day_pattern.rate_by_name("Peak")
        entity = sensor.DemandNowSensor(coordinator, day_pattern, rate)
        # No ledger exists yet and no refresh has run.
        coordinator.state.ledgers.clear()
        self.assertIsNone(entity.native_value)


class TestAllowanceUsedRestore(SensorCase):
    def test_restore_uses_slot_when_last_state_present(self) -> None:
        """Cover 551->553 true branch and value restore."""
        import asyncio

        coordinator = a_coordinator()
        day_pattern = coordinator.plan.day_pattern_by_name("Every day")
        rate = day_pattern.rate_by_name("Off Peak")
        entity = sensor.AllowanceUsedSensor(coordinator, day_pattern, rate)
        entity.hass = coordinator.hass

        class FakeRestored:
            native_value = "5.5"

        class FakeState:
            attributes: ClassVar[dict[str, Any]] = {
                CONST.ATTR_ALLOWANCE_SLOT: "slot-key"
            }

        sensor_mod = sys.modules["homeassistant.components.sensor"]
        sensor_mod.RestoreSensor.RESTORED = FakeRestored()
        sensor_mod.RestoreSensor.RESTORED_STATE = FakeState()

        # Ensure ledger exists with matching allowance key.
        ledger = coordinator.ledger(entity._qualified_name)
        ledger.allowance_key = "slot-key"

        asyncio.run(entity.async_added_to_hass())
        self.assertAlmostEqual(ledger.allowance_used_kwh, 5.5)

    def test_restore_ignored_when_last_state_missing(self) -> None:
        """Line 551->553 false branch: last state is None."""
        import asyncio

        coordinator = a_coordinator()
        day_pattern = coordinator.plan.day_pattern_by_name("Every day")
        rate = day_pattern.rate_by_name("Off Peak")
        entity = sensor.AllowanceUsedSensor(coordinator, day_pattern, rate)
        entity.hass = coordinator.hass

        class FakeRestored:
            native_value = "5.5"

        sensor_mod = sys.modules["homeassistant.components.sensor"]
        sensor_mod.RestoreSensor.RESTORED = FakeRestored()
        sensor_mod.RestoreSensor.RESTORED_STATE = None

        ledger = coordinator.ledger(entity._qualified_name)
        ledger.allowance_used_kwh = 0.0

        asyncio.run(entity.async_added_to_hass())
        self.assertAlmostEqual(ledger.allowance_used_kwh, 0.0)


class TestDemandPeakAtRestore(SensorCase):
    def test_restore_peak_at(self) -> None:
        """Lines 741, 744, 757-758."""
        import asyncio

        coordinator = a_coordinator()
        coordinator.async_refresh()
        day_pattern = coordinator.plan.day_pattern_by_name("Every day")
        rate = day_pattern.rate_by_name("Peak")
        entity = sensor.DemandPeakAtSensor(coordinator, day_pattern, rate)
        entity.hass = coordinator.hass

        class FakeRestored:
            native_value = "2026-08-14T10:00:00+10:00"

        class FakeState:
            attributes: ClassVar[dict[str, Any]] = {
                CONST.ATTR_CYCLE_START: coordinator.state.cycle_start.isoformat()
            }

        sensor_mod = sys.modules["homeassistant.components.sensor"]
        sensor_mod.RestoreSensor.RESTORED = FakeRestored()
        sensor_mod.RestoreSensor.RESTORED_STATE = FakeState()

        ledger = coordinator.ledger(entity._qualified_name)
        asyncio.run(entity.async_added_to_hass())
        self.assertIsNotNone(ledger.peak_at)

    def test_restore_peak_at_invalid_value_is_ignored(self) -> None:
        """Lines 746->748 and 757-758."""
        import asyncio

        coordinator = a_coordinator()
        coordinator.async_refresh()
        day_pattern = coordinator.plan.day_pattern_by_name("Every day")
        rate = day_pattern.rate_by_name("Peak")
        entity = sensor.DemandPeakAtSensor(coordinator, day_pattern, rate)
        entity.hass = coordinator.hass

        class FakeRestored:
            native_value = "not-a-timestamp"

        class FakeState:
            attributes: ClassVar[dict[str, Any]] = {
                CONST.ATTR_CYCLE_START: coordinator.state.cycle_start.isoformat()
            }

        sensor_mod = sys.modules["homeassistant.components.sensor"]
        sensor_mod.RestoreSensor.RESTORED = FakeRestored()
        sensor_mod.RestoreSensor.RESTORED_STATE = FakeState()

        ledger = coordinator.ledger(entity._qualified_name)
        asyncio.run(entity.async_added_to_hass())
        self.assertIsNone(ledger.peak_at)


class TestExportPriceSensor(SensorCase):
    def test_available_always_true(self) -> None:
        coordinator = a_coordinator()
        entity = sensor.ExportPriceSensor(coordinator, "AUD")
        self.assertTrue(entity.available)

    def test_native_value_with_flat_export(self) -> None:
        options = sample_options()
        pattern = options[CONST.CONF_DAY_PATTERNS][0]
        pattern[CONST.CONF_EXPORT_SAME_ALL_DAY] = True
        pattern[CONST.CONF_EXPORT_FLAT_CENTS] = 3.0
        pattern.pop(CONST.CONF_EXPORT_PERIODS, None)
        pattern.pop(CONST.CONF_EXPORT_RATES, None)
        coordinator = a_coordinator(options)
        entity = sensor.ExportPriceSensor(coordinator, "AUD")
        self.assertAlmostEqual(entity.native_value, 0.03)


if __name__ == "__main__":
    unittest.main()
