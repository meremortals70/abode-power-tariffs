"""Entities, setup, the action and diagnostics.

    python3 -m unittest tests.test_platform

These are the modules that were at zero coverage: sensor.py, binary_sensor.py,
__init__.py and diagnostics.py. They run against the same thin stubs as the
other suites.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import sys
import types
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _ha_stubs

_ha_stubs.install()

PACKAGE = "abode_power_tariffs_platform"
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
    "binary_sensor",
    "diagnostics",
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
SENSOR = sys.modules[f"{PACKAGE}.sensor"]
BINARY = sys.modules[f"{PACKAGE}.binary_sensor"]
DIAG = sys.modules[f"{PACKAGE}.diagnostics"]
COORD = sys.modules[f"{PACKAGE}.coordinator"]
PLAN = sys.modules[f"{PACKAGE}.plan"]
Plan = PLAN.Plan

BRISBANE = ZoneInfo("Australia/Brisbane")


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def options(**extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        CONST.CONF_DAY_PATTERNS: [
            {
                CONST.CONF_NAME: "Every day",
                CONST.CONF_DAYS: list(CONST.ALL_DAY_TOKENS),
                CONST.CONF_RATES: [
                    {
                        CONST.CONF_NAME: "Every day Off Peak",
                        CONST.CONF_IMPORT_CENTS: 19.8,
                        CONST.CONF_CONSTRAINTS: ["grid_charge_battery"],
                    },
                    {
                        CONST.CONF_NAME: "Every day Peak",
                        CONST.CONF_IMPORT_CENTS: 56.88,
                        CONST.CONF_CONSTRAINTS: ["no_grid_import"],
                    },
                ],
                CONST.CONF_PERIODS: [
                    {
                        CONST.CONF_START: "00:00",
                        CONST.CONF_END: "16:00",
                        CONST.CONF_RATE: "Every day Off Peak",
                    },
                    {
                        CONST.CONF_START: "16:00",
                        CONST.CONF_END: "24:00",
                        CONST.CONF_RATE: "Every day Peak",
                    },
                ],
                CONST.CONF_EXPORT_SAME_ALL_DAY: True,
                CONST.CONF_EXPORT_FLAT_CENTS: 2.7,
            }
        ],
        CONST.CONF_SUPPLY_CHARGE_CENTS: 116.6,
    }
    base.update(extra)
    return base


def rate_in(options: dict[str, Any], index: int, pattern: int = 0) -> dict[str, Any]:
    """Return one rate's own stored dict, nested inside its day pattern.

    Rates moved off the plan and onto the day pattern that owns them (Gap
    #1), so a fixture reaching a stored rate has one more level to go
    through than it used to.
    """
    return options[CONST.CONF_DAY_PATTERNS][pattern][CONST.CONF_RATES][index]


def peak_name(coordinator: Any, timetable: str = "Every day") -> str:
    """Return the qualified identifier of the sample plan's Peak rate."""
    day_pattern = coordinator.plan.day_pattern_by_name(timetable)
    if day_pattern is not None:
        for rate in day_pattern.rates:
            if rate.name == "Every day Peak":
                return PLAN.qualified_name(coordinator.plan.name, timetable, rate.name)
    raise AssertionError("no Peak rate on that timetable")


def off_peak_name(coordinator: Any, timetable: str = "Every day") -> str:
    """Return the qualified identifier of the sample plan's Off Peak rate."""
    day_pattern = coordinator.plan.day_pattern_by_name(timetable)
    if day_pattern is not None:
        for rate in day_pattern.rates:
            if rate.name == "Every day Off Peak":
                return PLAN.qualified_name(coordinator.plan.name, timetable, rate.name)
    raise AssertionError("no Off Peak rate on that timetable")


def a_coordinator(data: dict[str, Any] | None = None) -> Any:
    hass = _ha_stubs.FakeHass()
    data = data or options()
    plan = Plan.from_dict({**data, CONST.CONF_NAME: "Test"})
    coordinator = COORD.TariffCoordinator(hass, "entry1", plan, data)
    coordinator.async_refresh()
    return coordinator


class Added:
    """Captures what a platform hands to async_add_entities."""

    def __init__(self) -> None:
        self.entities: list[Any] = []

    def __call__(self, entities: Any) -> None:
        self.entities.extend(entities)

    def by_key(self, key: str) -> Any:
        for entity in self.entities:
            if entity._key == key:
                return entity
        raise AssertionError(f"no entity {key} in {[e._key for e in self.entities]}")


class FakeEntry:
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self.options = data or options()
        self.data = {CONST.CONF_PLAN_NAME: "Test Plan"}
        self.title = "Test Plan"
        self.entry_id = "entry1"
        self.domain = CONST.DOMAIN
        self.runtime_data: Any = None
        self.unloaded: list[Any] = []

    def add_update_listener(self, listener: Any) -> Any:
        return lambda: None

    def async_on_unload(self, func: Any) -> None:
        self.unloaded.append(func)


class PlatformCase(unittest.TestCase):
    def setUp(self) -> None:
        _ha_stubs.SCHEDULED.__init__()  # type: ignore[misc]
        COORD.dt_util.NOW = datetime(2026, 8, 14, 10, 0, tzinfo=BRISBANE)
        self.coordinator = a_coordinator()
        self.entry = FakeEntry()
        self.entry.runtime_data = self.coordinator
        self.added = Added()

    def tearDown(self) -> None:
        COORD.dt_util.NOW = None

    def sensors(self, data: dict[str, Any] | None = None) -> Added:
        if data is not None:
            self.coordinator = a_coordinator(data)
            self.entry.runtime_data = self.coordinator
        run(SENSOR.async_setup_entry(self.coordinator.hass, self.entry, self.added))
        return self.added


class TestSensorPlatform(PlatformCase):
    def test_the_sensors_always_present(self) -> None:
        """Five as before, plus the two accrual sensors rule 11 reinstated.

        The base fixture declares a daily supply charge, and rule 11 was
        revoked: a declared charge accumulates rather than sitting as a bare
        statement of itself, so the two accrual sensors are present whenever
        one is.
        """
        added = self.sensors()
        keys = {entity._key for entity in added.entities}
        self.assertEqual(
            keys,
            {
                "import_price",
                "export_price",
                "rate",
                "next_rate_change",
                "daily_supply_charge",
                "supply_charge_today",
                "supply_charge_energy",
            },
        )

    def test_import_price_is_dollars_per_kwh(self) -> None:
        sensor = self.sensors().by_key("import_price")
        self.assertAlmostEqual(sensor.native_value, 0.198)
        self.assertEqual(sensor._attr_native_unit_of_measurement, "AUD/kWh")

    def test_export_price_comes_from_the_timetable(self) -> None:
        sensor = self.sensors().by_key("export_price")
        self.assertAlmostEqual(sensor.native_value, 0.027)
        self.assertTrue(sensor.available)

    def test_price_attributes(self) -> None:
        sensor = self.sensors().by_key("import_price")
        attributes = sensor.extra_state_attributes
        self.assertEqual(attributes["rate"], off_peak_name(self.coordinator))
        self.assertEqual(attributes["period_start"], "00:00")
        self.assertEqual(attributes["period_end"], "16:00")
        self.assertEqual(attributes["day_pattern"], "Every day")
        self.assertEqual(attributes["constraints"], ["grid_charge_battery"])
        self.assertFalse(attributes["coasting_permitted"])
        self.assertFalse(attributes["plan_expired"])

    def test_the_forecast_attribute_is_evcc_shaped(self) -> None:
        sensor = self.sensors().by_key("import_price")
        forecast = sensor.extra_state_attributes["forecast"]
        self.assertTrue(forecast)
        self.assertEqual(set(forecast[0]), {"start", "end", "value"})
        # Local time with the offset, like everything else this publishes.
        self.assertFalse(forecast[0]["start"].endswith("Z"))
        self.assertTrue(forecast[0]["start"].endswith("+10:00"))

    def test_the_forecast_is_not_written_to_the_database(self) -> None:
        """A history of 24-hour predictions is tens of megabytes a day."""
        for key in ("import_price", "export_price"):
            sensor = self.sensors().by_key(key)
            self.assertIn("forecast", type(sensor)._unrecorded_attributes)

    def test_export_price_is_unknown_when_import_resolves_but_export_does_not(
        self,
    ) -> None:
        """P36. Was a fabricated $0.00 — import and export are separate
        flows (rule 5), so one resolving says nothing about the other.
        """
        data = options(
            **{
                CONST.CONF_DAY_PATTERNS: [
                    {
                        CONST.CONF_NAME: "Every day",
                        CONST.CONF_DAYS: list(CONST.ALL_DAY_TOKENS),
                        CONST.CONF_RATES: [
                            {
                                CONST.CONF_NAME: "Every day Off Peak",
                                CONST.CONF_IMPORT_CENTS: 19.8,
                            },
                            {
                                CONST.CONF_NAME: "Every day Peak",
                                CONST.CONF_IMPORT_CENTS: 56.88,
                            },
                        ],
                        CONST.CONF_PERIODS: [
                            {
                                CONST.CONF_START: "00:00",
                                CONST.CONF_END: "16:00",
                                CONST.CONF_RATE: "Every day Off Peak",
                            },
                            {
                                CONST.CONF_START: "16:00",
                                CONST.CONF_END: "24:00",
                                CONST.CONF_RATE: "Every day Peak",
                            },
                        ],
                        CONST.CONF_EXPORT_SAME_ALL_DAY: False,
                        # NOW is 10:00 (setUp) — this leaves it uncovered
                        # while every import period still resolves fine.
                        CONST.CONF_EXPORT_PERIODS: [
                            {
                                CONST.CONF_START: "14:00",
                                CONST.CONF_END: "24:00",
                                CONST.CONF_RATE: "Evening",
                            },
                        ],
                        CONST.CONF_EXPORT_RATES: [
                            {CONST.CONF_NAME: "Evening", CONST.CONF_EXPORT_CENTS: 8.0},
                        ],
                    }
                ],
            }
        )
        import_sensor = self.sensors(data).by_key("import_price")
        export_sensor = self.added.by_key("export_price")
        self.assertIsNotNone(import_sensor.native_value)
        self.assertIsNone(export_sensor.native_value)
        self.assertTrue(export_sensor.available)

    def test_export_price_attributes_are_export_specific(self) -> None:
        """P36. Used to share ImportPriceSensor's attributes wholesale —
        rate, day_pattern and the forecast were all import's own facts.
        """
        data = options(
            **{
                CONST.CONF_DAY_PATTERNS: [
                    {
                        CONST.CONF_NAME: "Every day",
                        CONST.CONF_DAYS: list(CONST.ALL_DAY_TOKENS),
                        CONST.CONF_RATES: [
                            {
                                CONST.CONF_NAME: "Every day Off Peak",
                                CONST.CONF_IMPORT_CENTS: 19.8,
                            }
                        ],
                        CONST.CONF_PERIODS: [
                            {
                                CONST.CONF_START: "00:00",
                                CONST.CONF_END: "24:00",
                                CONST.CONF_RATE: "Every day Off Peak",
                            },
                        ],
                        CONST.CONF_EXPORT_SAME_ALL_DAY: False,
                        CONST.CONF_EXPORT_PERIODS: [
                            {
                                CONST.CONF_START: "00:00",
                                CONST.CONF_END: "24:00",
                                CONST.CONF_RATE: "Evening",
                            },
                        ],
                        CONST.CONF_EXPORT_RATES: [
                            {
                                CONST.CONF_NAME: "Evening",
                                CONST.CONF_EXPORT_CENTS: 8.0,
                                CONST.CONF_EXPORT_ALLOWANCE_KWH: 5.0,
                                CONST.CONF_EXPORT_FALLBACK_CENTS: 3.0,
                            },
                        ],
                    }
                ],
            }
        )
        sensor = self.sensors(data).by_key("export_price")
        attributes = sensor.extra_state_attributes
        self.assertEqual(attributes["rate_name"], "Evening")
        self.assertEqual(attributes["period_start"], "00:00")
        self.assertEqual(attributes["period_end"], "24:00")
        self.assertEqual(attributes["day_pattern"], "Every day")
        self.assertAlmostEqual(attributes["allowance_kwh"], 5.0)
        self.assertAlmostEqual(attributes["fallback_per_kwh"], 0.03)
        self.assertFalse(attributes["plan_expired"])
        # None of these are import's facts, unlike the shared-attributes bug.
        self.assertNotEqual(attributes["rate_name"], "Every day Off Peak")

    def test_the_export_forecast_uses_export_prices_and_omits_gaps(self) -> None:
        """P36. evcc's own Rate.Price is non-optional, so an unresolved
        interval is left out of the list rather than sent as null.
        """
        data = options(
            **{
                CONST.CONF_DAY_PATTERNS: [
                    {
                        CONST.CONF_NAME: "Every day",
                        CONST.CONF_DAYS: list(CONST.ALL_DAY_TOKENS),
                        CONST.CONF_RATES: [
                            {
                                CONST.CONF_NAME: "Every day Off Peak",
                                CONST.CONF_IMPORT_CENTS: 19.8,
                            },
                        ],
                        CONST.CONF_PERIODS: [
                            {
                                CONST.CONF_START: "00:00",
                                CONST.CONF_END: "24:00",
                                CONST.CONF_RATE: "Every day Off Peak",
                            },
                        ],
                        CONST.CONF_EXPORT_SAME_ALL_DAY: False,
                        CONST.CONF_EXPORT_PERIODS: [
                            {
                                CONST.CONF_START: "14:00",
                                CONST.CONF_END: "24:00",
                                CONST.CONF_RATE: "Evening",
                            },
                        ],
                        CONST.CONF_EXPORT_RATES: [
                            {CONST.CONF_NAME: "Evening", CONST.CONF_EXPORT_CENTS: 8.0},
                        ],
                    }
                ],
            }
        )
        import_sensor = self.sensors(data).by_key("import_price")
        export_sensor = self.added.by_key("export_price")
        import_forecast = import_sensor.extra_state_attributes["forecast"]
        export_forecast = export_sensor.extra_state_attributes["forecast"]
        # Every import interval resolves (one all-day rate), so its series
        # is the full horizon. Export only resolves 14:00-24:00 each day,
        # so its series is shorter — the gap is left out, not nulled.
        self.assertLess(len(export_forecast), len(import_forecast))
        self.assertTrue(export_forecast)
        for entry in export_forecast:
            self.assertAlmostEqual(entry["value"], 0.08)

    def test_rate_sensor_is_an_enum_of_the_plan(self) -> None:
        sensor = self.sensors().by_key("rate")
        off_peak = off_peak_name(self.coordinator)
        peak = peak_name(self.coordinator)
        self.assertEqual(sensor.native_value, off_peak)
        self.assertEqual(sensor._attr_options, [off_peak, peak])
        self.assertEqual(sensor.extra_state_attributes["scheduled_rate"], off_peak)

    def test_next_rate_change_is_the_boundary(self) -> None:
        sensor = self.sensors().by_key("next_rate_change")
        assert sensor.native_value is not None
        self.assertEqual(sensor.native_value.astimezone(BRISBANE).hour, 16)

    def test_supply_charge_is_dollars_per_day_and_always_available(self) -> None:
        sensor = self.sensors().by_key("daily_supply_charge")
        self.assertAlmostEqual(sensor.native_value, 1.166)
        self.assertTrue(sensor.available)

    def test_no_export_change_sensor_on_a_flat_feed_in_price(self) -> None:
        keys = {entity._key for entity in self.sensors().entities}
        self.assertNotIn("next_export_change", keys)

    def test_the_export_change_sensor_appears_with_a_feed_in_schedule(self) -> None:
        data = options()
        pattern = data[CONST.CONF_DAY_PATTERNS][0]
        pattern[CONST.CONF_EXPORT_SAME_ALL_DAY] = False
        pattern[CONST.CONF_EXPORT_PERIODS] = [
            {
                CONST.CONF_START: "00:00",
                CONST.CONF_END: "09:00",
                CONST.CONF_RATE: "Night",
            },
            {
                CONST.CONF_START: "09:00",
                CONST.CONF_END: "16:00",
                CONST.CONF_RATE: "Day",
            },
            {
                CONST.CONF_START: "16:00",
                CONST.CONF_END: "24:00",
                CONST.CONF_RATE: "Night",
            },
        ]
        data[CONST.CONF_EXPORT_RATES] = [
            {CONST.CONF_NAME: "Night", CONST.CONF_EXPORT_CENTS: 0.0},
            {CONST.CONF_NAME: "Day", CONST.CONF_EXPORT_CENTS: 5.0},
        ]
        sensor = self.sensors(data).by_key("next_export_change")
        assert sensor.native_value is not None
        self.assertEqual(sensor.native_value.astimezone(BRISBANE).hour, 16)
        self.assertTrue(sensor.available)

    def _capped(self, **extra: Any) -> dict[str, Any]:
        data = options(**extra)
        rate_in(data, 0)[CONST.CONF_RATE_ALLOWANCE_KWH] = 24.0
        rate_in(data, 0)[CONST.CONF_FALLBACK_RATE] = "Every day Peak"
        return data

    def test_a_declared_cap_is_counted(self) -> None:
        """Rule 7, inverted.

        This test used to assert the opposite: that declaring a cap and
        counting against it were separate things and counting was opt-in.
        The rule was revoked, so the fact being asserted is now the other
        way round and is still worth holding. There is no tickbox — a plan
        that declares a cap and nominates a meter has it counted, because
        declaring a cap and refusing to count it means publishing a price
        that may already be wrong.
        """
        data = self._capped(**{CONST.CONF_IMPORT_ENERGY_SENSOR: "sensor.grid"})
        added = self.sensors(data)
        self.assertTrue(self.coordinator.counting_allowance)
        self.assertIn(
            "allowance_remaining_kwh", {entity._key for entity in added.entities}
        )

    def test_the_old_counting_tickbox_is_read_and_ignored(self) -> None:
        """A stored plan carries it. Rule 13 forbids migrating it away.

        An allowance that was declared but not counted starts being counted,
        which is the intended change. The stored key is read and ignored
        rather than renamed or removed.
        """
        off = self._capped(
            **{
                CONST.CONF_IMPORT_ENERGY_SENSOR: "sensor.grid",
                "count_allowance": False,
            }
        )
        self.sensors(off)
        self.assertTrue(self.coordinator.counting_allowance)

    def test_without_a_meter_the_price_is_the_scheduled_one(self) -> None:
        """Never the fallback, because nothing here knows the cap is spent.

        Rule 6 makes the meter required the moment a cap is declared, so this
        is a plan stored before that or one whose meter has been removed.
        """
        data = self._capped()
        sensor = self.sensors(data).by_key("import_price")
        self.assertAlmostEqual(sensor.native_value, 0.198)
        self.assertFalse(sensor.extra_state_attributes["allowance_counted"])
        self.assertFalse(sensor.extra_state_attributes["allowance_exhausted"])

    def test_with_a_meter_the_price_says_it_is_counted(self) -> None:
        data = self._capped(**{CONST.CONF_IMPORT_ENERGY_SENSOR: "sensor.grid"})
        sensor = self.sensors(data).by_key("import_price")
        self.assertTrue(sensor.extra_state_attributes["allowance_counted"])

    def test_counting_needs_a_meter(self) -> None:
        """The one thing that cannot be defaulted. Rule 6's own test."""
        data = self._capped()
        self.sensors(data)
        self.assertFalse(self.coordinator.counting_allowance)

    def test_no_allowance_sensor_without_an_energy_entity(self) -> None:
        keys = {entity._key for entity in self.sensors().entities}
        self.assertNotIn("allowance_remaining_kwh", keys)
        self.assertNotIn("allowance_used_kwh", keys)

    def test_the_allowance_sensor_appears_when_configured(self) -> None:
        data = options(**{CONST.CONF_IMPORT_ENERGY_SENSOR: "sensor.grid"})
        rate_in(data, 0)[CONST.CONF_RATE_ALLOWANCE_KWH] = 24.0
        rate_in(data, 0)[CONST.CONF_FALLBACK_RATE] = "Every day Peak"
        sensor = self.sensors(data).by_key("allowance_remaining_kwh")
        self.assertAlmostEqual(sensor.native_value, 24.0)
        self.assertTrue(sensor.available)

    def test_remaining_is_none_if_the_rate_is_unqualified(self) -> None:
        """The rate-is-None branch: the rate has been edited away from under it."""
        data = options(**{CONST.CONF_IMPORT_ENERGY_SENSOR: "sensor.grid"})
        rate_in(data, 0)[CONST.CONF_RATE_ALLOWANCE_KWH] = 24.0
        rate_in(data, 0)[CONST.CONF_FALLBACK_RATE] = "Every day Peak"
        sensor = self.sensors(data).by_key("allowance_remaining_kwh")
        sensor._rate_name = "No Such Rate"
        self.assertIsNone(sensor.native_value)

    def test_the_allowance_is_restored_across_a_restart(self) -> None:
        """The used sensor is what restores now; remaining is derived from it."""
        data = options(**{CONST.CONF_IMPORT_ENERGY_SENSOR: "sensor.grid"})
        rate_in(data, 0)[CONST.CONF_RATE_ALLOWANCE_KWH] = 24.0
        rate_in(data, 0)[CONST.CONF_FALLBACK_RATE] = "Every day Peak"
        added = self.sensors(data)
        used = added.by_key("allowance_used_kwh")
        used.hass = self.coordinator.hass
        module = _ha_stubs.sys.modules["homeassistant.components.sensor"]
        module.RestoreSensor.RESTORED = types.SimpleNamespace(native_value=15.0)
        # Recorded in the slot the component has come back into.
        ledger = self.coordinator.ledger_for(used._qualified_name)
        module.RestoreSensor.RESTORED_STATE = types.SimpleNamespace(
            attributes={CONST.ATTR_ALLOWANCE_SLOT: ledger.allowance_key}
        )
        run(used.async_added_to_hass())
        self.assertAlmostEqual(ledger.allowance_used_kwh, 15.0)
        remaining = added.by_key("allowance_remaining_kwh")
        self.assertAlmostEqual(remaining.native_value, 9.0)
        module.RestoreSensor.RESTORED = None
        module.RestoreSensor.RESTORED_STATE = None

    def test_a_count_from_another_slot_is_not_restored(self) -> None:
        """The allowance is the slot's. A figure from another one says nothing."""
        data = options(**{CONST.CONF_IMPORT_ENERGY_SENSOR: "sensor.grid"})
        rate_in(data, 0)[CONST.CONF_RATE_ALLOWANCE_KWH] = 24.0
        rate_in(data, 0)[CONST.CONF_FALLBACK_RATE] = "Every day Peak"
        added = self.sensors(data)
        used = added.by_key("allowance_used_kwh")
        used.hass = self.coordinator.hass
        module = _ha_stubs.sys.modules["homeassistant.components.sensor"]
        module.RestoreSensor.RESTORED = types.SimpleNamespace(native_value=9.0)
        module.RestoreSensor.RESTORED_STATE = types.SimpleNamespace(
            attributes={CONST.ATTR_ALLOWANCE_SLOT: "some.other@0-60/2001-01-01"}
        )
        run(used.async_added_to_hass())
        ledger = self.coordinator.ledger_for(used._qualified_name)
        self.assertEqual(ledger.allowance_used_kwh, 0.0)
        module.RestoreSensor.RESTORED = None
        module.RestoreSensor.RESTORED_STATE = None

    def test_the_supply_charge_accumulates(self) -> None:
        """Rule 11, inverted.

        This test used to assert the opposite: that the charge was a bare
        declaration and a total was the consumer's own arithmetic. The rule
        was revoked, so the fact worth holding is now that the two accrual
        sensors are present, and it is these that are asserted rather than
        the assertion being deleted.
        """
        keys = {entity._key for entity in self.sensors().entities}
        self.assertIn("daily_supply_charge", keys)
        self.assertIn("supply_charge_today", keys)
        self.assertIn("supply_charge_energy", keys)

    def test_the_used_sensor_reads_zero_before_any_energy_is_recorded(self) -> None:
        """The fixture refreshes on construction, so a ledger exists at zero."""
        data = options(**{CONST.CONF_IMPORT_ENERGY_SENSOR: "sensor.grid"})
        rate_in(data, 0)[CONST.CONF_RATE_ALLOWANCE_KWH] = 24.0
        rate_in(data, 0)[CONST.CONF_FALLBACK_RATE] = "Every day Peak"
        added = self.sensors(data)
        used = added.by_key("allowance_used_kwh")
        self.assertEqual(used.native_value, 0.0)

    def test_the_used_sensor_is_none_if_the_rate_is_unqualified(self) -> None:
        """The ledger-is-None branch: no such rate, so no ledger to read."""
        data = options(**{CONST.CONF_IMPORT_ENERGY_SENSOR: "sensor.grid"})
        rate_in(data, 0)[CONST.CONF_RATE_ALLOWANCE_KWH] = 24.0
        rate_in(data, 0)[CONST.CONF_FALLBACK_RATE] = "Every day Peak"
        added = self.sensors(data)
        used = added.by_key("allowance_used_kwh")
        used._qualified_name = "no.such.rate"
        self.assertIsNone(used.native_value)

    def test_the_used_sensor_reads_the_ledger_once_one_exists(self) -> None:
        data = options(**{CONST.CONF_IMPORT_ENERGY_SENSOR: "sensor.grid"})
        rate_in(data, 0)[CONST.CONF_RATE_ALLOWANCE_KWH] = 24.0
        rate_in(data, 0)[CONST.CONF_FALLBACK_RATE] = "Every day Peak"
        added = self.sensors(data)
        used = added.by_key("allowance_used_kwh")
        self.coordinator.async_refresh()
        ledger = self.coordinator.ledger_for(used._qualified_name)
        ledger.allowance_used_kwh = 7.5
        self.assertAlmostEqual(used.native_value, 7.5)

    def test_the_used_sensors_attributes_name_the_declaration(self) -> None:
        data = options(**{CONST.CONF_IMPORT_ENERGY_SENSOR: "sensor.grid"})
        rate_in(data, 0)[CONST.CONF_RATE_ALLOWANCE_KWH] = 24.0
        rate_in(data, 0)[CONST.CONF_FALLBACK_RATE] = "Every day Peak"
        rate_in(data, 0)[CONST.CONF_ALLOWANCE_PERIOD] = "month"
        added = self.sensors(data)
        used = added.by_key("allowance_used_kwh")
        self.coordinator.async_refresh()
        attrs = used.extra_state_attributes
        self.assertEqual(attrs["allowance_period"], "month")
        self.assertAlmostEqual(attrs["allowance_kwh"], 24.0)
        self.assertIn(CONST.ATTR_ESTIMATE, attrs)
        self.assertEqual(attrs[CONST.ATTR_QUALIFIED_RATE], used._qualified_name)

    def test_the_used_sensor_ignores_a_restore_with_no_stored_value(self) -> None:
        """`_restored_value` returns None when there is nothing to read."""
        data = options(**{CONST.CONF_IMPORT_ENERGY_SENSOR: "sensor.grid"})
        rate_in(data, 0)[CONST.CONF_RATE_ALLOWANCE_KWH] = 24.0
        rate_in(data, 0)[CONST.CONF_FALLBACK_RATE] = "Every day Peak"
        added = self.sensors(data)
        used = added.by_key("allowance_used_kwh")
        used.hass = self.coordinator.hass
        self.coordinator.async_refresh()
        module = _ha_stubs.sys.modules["homeassistant.components.sensor"]
        module.RestoreSensor.RESTORED = None
        module.RestoreSensor.RESTORED_STATE = None
        run(used.async_added_to_hass())
        ledger = self.coordinator.ledger_for(used._qualified_name)
        self.assertEqual(ledger.allowance_used_kwh, 0.0)

    def test_the_used_sensor_ignores_a_restored_value_that_is_not_a_number(
        self,
    ) -> None:
        data = options(**{CONST.CONF_IMPORT_ENERGY_SENSOR: "sensor.grid"})
        rate_in(data, 0)[CONST.CONF_RATE_ALLOWANCE_KWH] = 24.0
        rate_in(data, 0)[CONST.CONF_FALLBACK_RATE] = "Every day Peak"
        added = self.sensors(data)
        used = added.by_key("allowance_used_kwh")
        used.hass = self.coordinator.hass
        self.coordinator.async_refresh()
        module = _ha_stubs.sys.modules["homeassistant.components.sensor"]
        module.RestoreSensor.RESTORED = types.SimpleNamespace(
            native_value="not-a-number"
        )
        module.RestoreSensor.RESTORED_STATE = None
        run(used.async_added_to_hass())
        ledger = self.coordinator.ledger_for(used._qualified_name)
        self.assertEqual(ledger.allowance_used_kwh, 0.0)
        module.RestoreSensor.RESTORED = None

    def test_the_used_sensor_ignores_a_restore_with_no_matching_rate(self) -> None:
        """The ledger-is-None branch: the rate no longer exists to restore onto."""
        data = options(**{CONST.CONF_IMPORT_ENERGY_SENSOR: "sensor.grid"})
        rate_in(data, 0)[CONST.CONF_RATE_ALLOWANCE_KWH] = 24.0
        rate_in(data, 0)[CONST.CONF_FALLBACK_RATE] = "Every day Peak"
        added = self.sensors(data)
        used = added.by_key("allowance_used_kwh")
        used.hass = self.coordinator.hass
        used._qualified_name = "no.such.rate"
        module = _ha_stubs.sys.modules["homeassistant.components.sensor"]
        module.RestoreSensor.RESTORED = types.SimpleNamespace(native_value=9.0)
        module.RestoreSensor.RESTORED_STATE = None
        # Nothing to assert on a ledger that cannot exist; this exercises the
        # early return and confirms it does not raise.
        run(used.async_added_to_hass())
        module.RestoreSensor.RESTORED = None


class TestDemandSensors(PlatformCase):
    def _demand_data(self) -> dict[str, Any]:
        data = options(**{CONST.CONF_IMPORT_ENERGY_SENSOR: "sensor.grid"})
        rate_in(data, 1)[CONST.CONF_DEMAND_PERIOD] = True
        rate_in(data, 1)[CONST.CONF_DEMAND_RATE] = 20.0
        return data

    def test_the_demand_sensors_appear_only_for_a_rate_that_declares_one(self) -> None:
        added = self.sensors(self._demand_data())
        keys = {entity._key for entity in added.entities}
        self.assertIn("demand_now_kw", keys)
        self.assertIn("demand_peak_kw", keys)
        self.assertIn("demand_peak_at", keys)
        self.assertIn("demand_cost_to_date", keys)
        self.assertIn("demand_cost_projected", keys)

    def test_no_demand_sensors_when_nothing_declares_a_demand_charge(self) -> None:
        keys = {entity._key for entity in self.sensors().entities}
        self.assertNotIn("demand_peak_kw", keys)

    def test_the_peak_sensor_reads_the_ledger(self) -> None:
        added = self.sensors(self._demand_data())
        sensor = added.by_key("demand_peak_kw")
        ledger = self.coordinator.ledger_for(sensor._qualified_name)
        ledger.peak_kw = 5.0
        self.assertAlmostEqual(sensor.native_value, 5.0)

    def test_the_projected_cost_uses_the_whole_cycle(self) -> None:
        added = self.sensors(self._demand_data())
        sensor = added.by_key("demand_cost_projected")
        ledger = self.coordinator.ledger_for(sensor._qualified_name)
        ledger.peak_kw = 5.0
        self.coordinator.state.days_in_cycle = 31
        # 5 kW at $20/kW/day over 31 days.
        self.assertAlmostEqual(sensor.native_value, 5.0 * 20.0 * 31, places=2)

    def test_the_cost_sensors_are_none_before_anything_accumulates(self) -> None:
        added = self.sensors(self._demand_data())
        sensor = added.by_key("demand_cost_to_date")
        self.coordinator.state.ledgers.clear()
        self.assertIsNone(sensor.native_value)

    def test_the_peak_at_sensor_reports_when_it_was_set(self) -> None:
        added = self.sensors(self._demand_data())
        sensor = added.by_key("demand_peak_at")
        self.assertIsNone(sensor.native_value)
        ledger = self.coordinator.ledger_for(sensor._qualified_name)
        moment = datetime(2026, 5, 20, 17, 30, tzinfo=BRISBANE)
        ledger.peak_at = moment
        self.assertEqual(sensor.native_value, moment)

    def test_an_unqualified_rate_makes_the_entity_unavailable(self) -> None:
        """If the rate is edited away from under it, the entity says so."""
        added = self.sensors(self._demand_data())
        sensor = added.by_key("demand_peak_kw")
        sensor._rate_name = "No Such Rate"
        self.assertFalse(sensor.available)

    def test_the_peak_restores_when_it_belongs_to_the_current_cycle(self) -> None:
        added = self.sensors(self._demand_data())
        sensor = added.by_key("demand_peak_kw")
        sensor.hass = self.coordinator.hass
        self.coordinator.async_refresh()
        cycle = self.coordinator.state.cycle_start.isoformat()
        module = _ha_stubs.sys.modules["homeassistant.components.sensor"]
        module.RestoreSensor.RESTORED = types.SimpleNamespace(native_value=5.0)
        module.RestoreSensor.RESTORED_STATE = types.SimpleNamespace(
            attributes={CONST.ATTR_CYCLE_START: cycle}
        )
        run(sensor.async_added_to_hass())
        ledger = self.coordinator.ledger_for(sensor._qualified_name)
        self.assertAlmostEqual(ledger.peak_kw, 5.0)
        module.RestoreSensor.RESTORED = None
        module.RestoreSensor.RESTORED_STATE = None

    def test_a_peak_from_a_different_cycle_is_discarded(self) -> None:
        added = self.sensors(self._demand_data())
        sensor = added.by_key("demand_peak_kw")
        sensor.hass = self.coordinator.hass
        self.coordinator.async_refresh()
        module = _ha_stubs.sys.modules["homeassistant.components.sensor"]
        module.RestoreSensor.RESTORED = types.SimpleNamespace(native_value=5.0)
        module.RestoreSensor.RESTORED_STATE = types.SimpleNamespace(
            attributes={CONST.ATTR_CYCLE_START: "2001-01-01"}
        )
        run(sensor.async_added_to_hass())
        ledger = self.coordinator.ledger_for(sensor._qualified_name)
        self.assertEqual(ledger.peak_kw, 0.0)
        module.RestoreSensor.RESTORED = None
        module.RestoreSensor.RESTORED_STATE = None

    def test_a_peak_restore_with_nothing_stored_does_nothing(self) -> None:
        added = self.sensors(self._demand_data())
        sensor = added.by_key("demand_peak_kw")
        sensor.hass = self.coordinator.hass
        self.coordinator.async_refresh()
        module = _ha_stubs.sys.modules["homeassistant.components.sensor"]
        module.RestoreSensor.RESTORED = None
        module.RestoreSensor.RESTORED_STATE = None
        run(sensor.async_added_to_hass())
        ledger = self.coordinator.ledger_for(sensor._qualified_name)
        self.assertEqual(ledger.peak_kw, 0.0)

    def test_a_non_numeric_restored_peak_is_ignored(self) -> None:
        added = self.sensors(self._demand_data())
        sensor = added.by_key("demand_peak_kw")
        sensor.hass = self.coordinator.hass
        self.coordinator.async_refresh()
        cycle = self.coordinator.state.cycle_start.isoformat()
        module = _ha_stubs.sys.modules["homeassistant.components.sensor"]
        module.RestoreSensor.RESTORED = types.SimpleNamespace(native_value="oops")
        module.RestoreSensor.RESTORED_STATE = types.SimpleNamespace(
            attributes={CONST.ATTR_CYCLE_START: cycle}
        )
        run(sensor.async_added_to_hass())
        ledger = self.coordinator.ledger_for(sensor._qualified_name)
        self.assertEqual(ledger.peak_kw, 0.0)
        module.RestoreSensor.RESTORED = None
        module.RestoreSensor.RESTORED_STATE = None

    def test_a_peak_restore_with_no_matching_rate_does_nothing(self) -> None:
        """The ledger-is-None branch of the peak sensor's own restore method."""
        added = self.sensors(self._demand_data())
        sensor = added.by_key("demand_peak_kw")
        sensor.hass = self.coordinator.hass
        sensor._qualified_name = "no.such.rate"
        module = _ha_stubs.sys.modules["homeassistant.components.sensor"]
        module.RestoreSensor.RESTORED = types.SimpleNamespace(native_value=5.0)
        module.RestoreSensor.RESTORED_STATE = None
        run(sensor.async_added_to_hass())
        module.RestoreSensor.RESTORED = None

    def test_the_now_sensor_is_none_if_the_rate_is_unqualified(self) -> None:
        added = self.sensors(self._demand_data())
        sensor = added.by_key("demand_now_kw")
        sensor._qualified_name = "no.such.rate"
        self.assertIsNone(sensor.native_value)

    def test_a_peak_restore_with_no_last_state_still_checks_the_value(self) -> None:
        """The last-state-is-None branch: only the sensor value was recorded."""
        added = self.sensors(self._demand_data())
        sensor = added.by_key("demand_peak_kw")
        sensor.hass = self.coordinator.hass
        self.coordinator.async_refresh()
        module = _ha_stubs.sys.modules["homeassistant.components.sensor"]
        module.RestoreSensor.RESTORED = types.SimpleNamespace(native_value=5.0)
        module.RestoreSensor.RESTORED_STATE = None
        run(sensor.async_added_to_hass())
        ledger = self.coordinator.ledger_for(sensor._qualified_name)
        # No cycle recorded, so it cannot match the current one.
        self.assertEqual(ledger.peak_kw, 0.0)
        module.RestoreSensor.RESTORED = None

    def test_the_peak_attributes_omit_the_basis_if_the_rate_is_unqualified(
        self,
    ) -> None:
        added = self.sensors(self._demand_data())
        sensor = added.by_key("demand_peak_kw")
        sensor._rate_name = "No Such Rate"
        attrs = sensor.extra_state_attributes
        self.assertNotIn("demand_interval", attrs)

    def test_the_peak_sensors_attributes_carry_the_declared_basis(self) -> None:
        added = self.sensors(self._demand_data())
        sensor = added.by_key("demand_peak_kw")
        self.coordinator.async_refresh()
        attrs = sensor.extra_state_attributes
        self.assertEqual(attrs["demand_interval"], 30)
        self.assertEqual(attrs["demand_basis"], "day")


class TestBillingCycleSensor(PlatformCase):
    def test_no_progress_sensor_when_the_plan_accounts_for_nothing(self) -> None:
        keys = {entity._key for entity in self.sensors().entities}
        self.assertNotIn("billing_cycle_progress", keys)

    def test_progress_is_none_if_the_cycle_has_no_length(self) -> None:
        """The guard branch: days_in_cycle at its unset default."""
        data = options(**{CONST.CONF_IMPORT_ENERGY_SENSOR: "sensor.grid"})
        rate_in(data, 0)[CONST.CONF_RATE_ALLOWANCE_KWH] = 24.0
        rate_in(data, 0)[CONST.CONF_FALLBACK_RATE] = "Every day Peak"
        added = self.sensors(data)
        sensor = added.by_key("billing_cycle_progress")
        self.coordinator.state.days_in_cycle = 0
        self.assertIsNone(sensor.native_value)

    def test_progress_appears_when_the_plan_accounts(self) -> None:
        data = options(**{CONST.CONF_IMPORT_ENERGY_SENSOR: "sensor.grid"})
        rate_in(data, 0)[CONST.CONF_RATE_ALLOWANCE_KWH] = 24.0
        rate_in(data, 0)[CONST.CONF_FALLBACK_RATE] = "Every day Peak"
        added = self.sensors(data)
        sensor = added.by_key("billing_cycle_progress")
        self.coordinator.state.days_elapsed = 10
        self.coordinator.state.days_in_cycle = 31
        self.assertAlmostEqual(sensor.native_value, round(1000 / 31, 1))
        self.assertTrue(sensor.available)

    def test_progress_attributes_carry_the_cycle_dates(self) -> None:
        data = options(**{CONST.CONF_IMPORT_ENERGY_SENSOR: "sensor.grid"})
        rate_in(data, 0)[CONST.CONF_RATE_ALLOWANCE_KWH] = 24.0
        rate_in(data, 0)[CONST.CONF_FALLBACK_RATE] = "Every day Peak"
        added = self.sensors(data)
        sensor = added.by_key("billing_cycle_progress")
        self.coordinator.async_refresh()
        attrs = sensor.extra_state_attributes
        self.assertIsNotNone(attrs[CONST.ATTR_CYCLE_START])
        self.assertIsNotNone(attrs[CONST.ATTR_CYCLE_END])
        self.assertEqual(
            attrs["days_remaining"], attrs["days_in_cycle"] - attrs["days_elapsed"]
        )
        self.assertEqual(
            attrs["billing_cycle_day"], self.coordinator.plan.billing_cycle_day
        )
        self.assertIn(CONST.ATTR_CYCLE_COMPLETE, attrs)


class TestSupplyChargeAccrualSensors(PlatformCase):
    def test_today_reads_the_coordinator_state(self) -> None:
        sensor = self.sensors().by_key("supply_charge_today")
        self.coordinator.state.supply_charge_today = 0.5
        self.assertAlmostEqual(sensor.native_value, 0.5)
        self.assertTrue(sensor.available)

    def test_cycle_reads_the_coordinator_state(self) -> None:
        sensor = self.sensors().by_key("supply_charge_energy")
        self.coordinator.state.supply_charge_cycle = 3.0
        self.assertAlmostEqual(sensor.native_value, 3.0)

    def test_the_accrual_attributes_say_it_is_an_estimate(self) -> None:
        added = self.sensors()
        today = added.by_key("supply_charge_today")
        self.coordinator.async_refresh()
        attrs = today.extra_state_attributes
        self.assertIn(CONST.ATTR_ESTIMATE, attrs)
        self.assertIsNotNone(attrs[CONST.ATTR_CYCLE_START])
        self.assertIsNotNone(attrs[CONST.ATTR_CYCLE_END])
        self.assertIn(CONST.ATTR_CYCLE_COMPLETE, attrs)

    def test_the_daily_supply_charge_sensor_names_the_cycle_too(self) -> None:
        """Rule 11: the declared figure and its accrual are no longer separate
        stories, so the plain declaration also carries the cycle dates."""
        added = self.sensors()
        declared = added.by_key("daily_supply_charge")
        self.coordinator.async_refresh()
        attrs = declared.extra_state_attributes
        self.assertIsNotNone(attrs[CONST.ATTR_CYCLE_START])
        self.assertIsNotNone(attrs[CONST.ATTR_CYCLE_END])


class TestBinarySensorPlatform(PlatformCase):
    def _added(self) -> Added:
        run(BINARY.async_setup_entry(self.coordinator.hass, self.entry, self.added))
        return self.added

    def test_one_per_declared_constraint(self) -> None:
        keys = {entity._key for entity in self._added().entities}
        self.assertEqual(
            keys, {"constraint_grid_charge_battery", "constraint_no_grid_import"}
        )

    def test_on_only_while_its_rate_is_in_force(self) -> None:
        added = self._added()
        charge = added.by_key("constraint_grid_charge_battery")
        peak = added.by_key("constraint_no_grid_import")
        self.assertTrue(charge.is_on)
        self.assertFalse(peak.is_on)

        COORD.dt_util.NOW = datetime(2026, 8, 14, 17, 0, tzinfo=BRISBANE)
        self.coordinator.async_refresh()
        self.assertFalse(charge.is_on)
        self.assertTrue(peak.is_on)

    def test_attributes_name_the_period(self) -> None:
        charge = self._added().by_key("constraint_grid_charge_battery")
        attributes = charge.extra_state_attributes
        self.assertEqual(attributes["constraint"], "grid_charge_battery")
        self.assertEqual(attributes["period_end"], "16:00")

    def test_attributes_are_bare_when_off(self) -> None:
        peak = self._added().by_key("constraint_no_grid_import")
        self.assertEqual(
            peak.extra_state_attributes,
            {"constraint": "no_grid_import", "enforceable": False},
        )

    def test_the_rule_says_whether_it_is_enforceable(self) -> None:
        """A declaration about what the rate means. Nothing is enforced here."""
        data = options()
        rate_in(data, 1)[CONST.CONF_ENFORCEABLE_CONSTRAINTS] = ["no_grid_import"]
        self.coordinator = a_coordinator(data)
        self.entry.runtime_data = self.coordinator
        added = self._added()
        peak = added.by_key("constraint_no_grid_import")
        charge = added.by_key("constraint_grid_charge_battery")

        COORD.dt_util.NOW = datetime(2026, 8, 14, 17, 0, tzinfo=BRISBANE)
        self.coordinator.async_refresh()
        self.assertTrue(peak.is_on)
        self.assertTrue(peak.extra_state_attributes["enforceable"])
        self.assertFalse(charge.extra_state_attributes["enforceable"])

    def test_the_name_is_readable(self) -> None:
        charge = self._added().by_key("constraint_grid_charge_battery")
        self.assertEqual(charge._attr_name, "Grid charge battery")
        self.assertIsNone(charge._attr_translation_key)

    def test_the_demand_sensor_is_absent_when_no_rate_has_one(self) -> None:
        """A plan with no demand charge gets no entity that is permanently off."""
        keys = {entity._key for entity in self._added().entities}
        self.assertNotIn("demand_period_active", keys)

    def test_the_demand_sensor_appears_when_a_rate_has_one(self) -> None:
        data = options()
        rate_in(data, 1)[CONST.CONF_DEMAND_PERIOD] = True
        rate_in(data, 1)[CONST.CONF_DEMAND_RATE] = 18.4
        self.coordinator = a_coordinator(data)
        self.entry.runtime_data = self.coordinator
        keys = {entity._key for entity in self._added().entities}
        self.assertIn("demand_period_active", keys)

    def test_the_demand_sensor_is_on_only_while_its_rate_is_in_force(self) -> None:
        """One sensor per rate now (rule 10), not one per plan.

        Its attributes describe the rate it belongs to, not whichever rate
        happens to be in force — that is the whole point of moving it off the
        plan, so a demand charge on a rate that is not currently active still
        has something to say about itself.
        """
        data = options()
        rate_in(data, 1)[CONST.CONF_DEMAND_PERIOD] = True
        rate_in(data, 1)[CONST.CONF_DEMAND_RATE] = 18.4
        self.coordinator = a_coordinator(data)
        self.entry.runtime_data = self.coordinator
        demand = self._added().by_key("demand_period_active")

        # "Every day Off Peak" is in force at setup (COORD.dt_util.NOW default).
        # Peak is not, but it still declares 18.4 c/kW/day about itself.
        self.assertFalse(demand.is_on)
        self.assertAlmostEqual(
            demand.extra_state_attributes["demand_rate_per_kw_month"], 18.4
        )

        COORD.dt_util.NOW = datetime(2026, 8, 14, 17, 0, tzinfo=BRISBANE)
        self.coordinator.async_refresh()
        self.assertTrue(demand.is_on)
        self.assertAlmostEqual(
            demand.extra_state_attributes["demand_rate_per_kw_month"], 18.4
        )

    def test_no_data_complete_sensor_when_the_plan_accounts_for_nothing(self) -> None:
        keys = {entity._key for entity in self._added().entities}
        self.assertNotIn("data_complete", keys)

    def test_data_complete_appears_when_the_plan_accounts(self) -> None:
        data = options(**{CONST.CONF_IMPORT_ENERGY_SENSOR: "sensor.grid"})
        rate_in(data, 0)[CONST.CONF_RATE_ALLOWANCE_KWH] = 24.0
        rate_in(data, 0)[CONST.CONF_FALLBACK_RATE] = "Every day Peak"
        self.coordinator = a_coordinator(data)
        self.entry.runtime_data = self.coordinator
        sensor = self._added().by_key("data_complete")
        self.assertFalse(sensor.is_on)
        self.coordinator.state.data_complete = False
        self.coordinator.state.cycle_complete = False
        self.assertTrue(sensor.is_on)
        self.assertFalse(sensor.extra_state_attributes["cycle_complete"])


class TestSetupAndUnload(PlatformCase):
    def setUp(self) -> None:
        super().setUp()
        self.forwarded: list[Any] = []
        issues = sys.modules["homeassistant.helpers.issue_registry"]
        issues.RAISED.clear()
        issues.DELETED.clear()

        class FakeConfigEntries:
            def __init__(self, outer: Any) -> None:
                self.outer = outer

            async def async_forward_entry_setups(
                self, entry: Any, platforms: Any
            ) -> None:
                self.outer.forwarded.append(list(platforms))

            async def async_unload_platforms(self, entry: Any, platforms: Any) -> bool:
                return True

            def async_get_entry(self, entry_id: str) -> Any:
                return self.outer.entry if entry_id == "entry1" else None

            def async_update_entry(self, entry: Any, **kwargs: Any) -> None:
                for key, value in kwargs.items():
                    setattr(entry, key, value)

        self.coordinator.hass.config_entries = FakeConfigEntries(self)

    def test_setup_creates_the_coordinator_and_forwards_platforms(self) -> None:
        entry = FakeEntry()
        hass = self.coordinator.hass
        self.assertTrue(run(PKG.async_setup_entry(hass, entry)))
        self.assertIsNotNone(entry.runtime_data)
        self.assertEqual(self.forwarded, [["binary_sensor", "sensor"]])

    def test_a_valid_plan_clears_the_repair_issue(self) -> None:
        run(PKG.async_setup_entry(self.coordinator.hass, FakeEntry()))
        issues = sys.modules["homeassistant.helpers.issue_registry"]
        self.assertEqual(issues.RAISED, [])
        self.assertEqual(issues.DELETED, ["invalid_plan_entry1"])

    def test_an_invalid_plan_raises_a_repair_issue_and_still_sets_up(self) -> None:
        broken = options()
        broken[CONST.CONF_DAY_PATTERNS][0][CONST.CONF_PERIODS].pop()
        entry = FakeEntry(broken)
        self.assertTrue(run(PKG.async_setup_entry(self.coordinator.hass, entry)))
        issues = sys.modules["homeassistant.helpers.issue_registry"]
        self.assertEqual(len(issues.RAISED), 1)
        self.assertIn("problems", issues.RAISED[0][1]["translation_placeholders"])

    def test_an_unreadable_plan_defers_setup(self) -> None:
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        entry = FakeEntry(
            {
                CONST.CONF_DAY_PATTERNS: [
                    {
                        CONST.CONF_NAME: "Every day",
                        CONST.CONF_DAYS: list(CONST.ALL_DAY_TOKENS),
                        # No name: Rate.from_dict raises PlanError.
                        CONST.CONF_RATES: [{CONST.CONF_IMPORT_CENTS: 1}],
                    }
                ]
            }
        )
        not_ready = sys.modules["homeassistant.exceptions"].ConfigEntryNotReady
        with self.assertRaises(not_ready):
            run(PKG.async_setup_entry(self.coordinator.hass, entry))

    def test_unload_shuts_the_coordinator_down(self) -> None:
        entry = FakeEntry()
        run(PKG.async_setup_entry(self.coordinator.hass, entry))
        self.assertTrue(run(PKG.async_unload_entry(self.coordinator.hass, entry)))


class TestTheAction(PlatformCase):
    def setUp(self) -> None:
        super().setUp()
        self.registered: dict[str, Any] = {}
        outer = self

        class FakeServices(_ha_stubs.FakeServices):
            def async_register(
                self, domain: str, service: str, handler: Any, **kwargs: Any
            ) -> None:
                outer.registered[service] = handler

        self.coordinator.hass.services = FakeServices()

        class FakeConfigEntries:
            def async_get_entry(self, entry_id: str) -> Any:
                return outer.entry if entry_id == "entry1" else None

        self.coordinator.hass.config_entries = FakeConfigEntries()
        run(PKG.async_setup(self.coordinator.hass, {}))

    def _call(self, **data: Any) -> Any:
        payload = {CONST.ATTR_HOURS: 6, CONST.ATTR_RESOLUTION_MINUTES: 30}
        payload.update(data)
        return run(
            self.registered[CONST.SERVICE_GET_INTERVALS](
                types.SimpleNamespace(data=payload)
            )
        )

    def test_the_action_is_registered(self) -> None:
        self.assertIn(CONST.SERVICE_GET_INTERVALS, self.registered)

    def test_it_returns_the_forward_series(self) -> None:
        response = self._call(**{CONST.ATTR_CONFIG_ENTRY_ID: "entry1"})
        self.assertEqual(len(response["intervals"]), 12)
        self.assertEqual(
            response["intervals"][0]["rate"], off_peak_name(self.coordinator)
        )

    def test_an_unknown_entry_is_a_validation_error(self) -> None:
        error = sys.modules["homeassistant.exceptions"].ServiceValidationError
        with self.assertRaises(error):
            self._call(**{CONST.ATTR_CONFIG_ENTRY_ID: "nope"})

    def test_an_unloaded_entry_is_a_validation_error(self) -> None:
        self.entry.runtime_data = None
        error = sys.modules["homeassistant.exceptions"].ServiceValidationError
        with self.assertRaises(error):
            self._call(**{CONST.ATTR_CONFIG_ENTRY_ID: "entry1"})


class TestDiagnostics(PlatformCase):
    def test_everything_needed_to_reason_offline(self) -> None:
        payload = run(
            DIAG.async_get_config_entry_diagnostics(self.coordinator.hass, self.entry)
        )
        for key in (
            "plan",
            "rates_csv",
            "periods_csv",
            "strip",
            "rate_plan_card",
            "problems",
            "current",
            "options",
            "intervals",
        ):
            self.assertIn(key, payload)
        self.assertEqual(payload["problems"], [])
        self.assertEqual(payload["current"]["rate"], off_peak_name(self.coordinator))
        self.assertNotIn("rates", payload["options"])


if __name__ == "__main__":
    unittest.main()
