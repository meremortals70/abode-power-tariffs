"""Additional coordinator tests for the uncovered edge cases.

These live in their own file so the main runtime test file does not grow
unwieldy; the package loader is the same one used by tests.test_runtime.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _ha_stubs

_ha_stubs.install()

PACKAGE = "abode_power_tariffs_runtime"
ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "abode_power_tariffs"
MODULES = (
    "const",
    "plan",
    "validate",
    "intervals",
    "allowance",
    "strip",
    "serialise",
    "coordinator",
    "entity",
    "config_flow",
)


def _load() -> types.ModuleType:
    if PACKAGE in sys.modules:
        return sys.modules[PACKAGE]
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(ROOT)]
    sys.modules[PACKAGE] = package
    for name in MODULES:
        spec = importlib.util.spec_from_file_location(
            f"{PACKAGE}.{name}", ROOT / f"{name}.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"{PACKAGE}.{name}"] = module
        spec.loader.exec_module(module)
        setattr(package, name, module)
    return package


PKG = _load()
CONST = PKG.const
Plan = PKG.plan.Plan
TariffCoordinator = PKG.coordinator.TariffCoordinator
BRISBANE = ZoneInfo("Australia/Brisbane")


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def at(hour: int, minute: int = 0, day: int = 14) -> Any:
    from datetime import datetime

    return datetime(2026, 8, day, hour, minute, tzinfo=BRISBANE)


def today() -> Any:
    return at(10).date()


def sample_options() -> dict[str, Any]:
    return {
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
                CONST.CONF_EXPORT_SAME_ALL_DAY: True,
                CONST.CONF_EXPORT_FLAT_CENTS: 2.7,
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


def rate_in(options: dict[str, Any], index: int, pattern: int = 0) -> dict[str, Any]:
    return options[CONST.CONF_DAY_PATTERNS][pattern][CONST.CONF_RATES][index]


class CoordinatorCase(unittest.TestCase):
    def setUp(self) -> None:
        _ha_stubs.SCHEDULED.__init__()  # type: ignore[misc]
        PKG.coordinator.dt_util.NOW = at(10)

    def tearDown(self) -> None:
        PKG.coordinator.dt_util.NOW = None


class TestStartupAndShutdown(CoordinatorCase):
    def test_start_with_no_tracked_entities_does_not_register_a_listener(self) -> None:
        """Line 219: no holiday, import or export sensor configured."""
        coordinator = a_coordinator()
        coordinator._seed_retry_delay_seconds = 0
        run(coordinator.async_start())
        self.assertEqual(
            len(_ha_stubs.SCHEDULED.state_listeners), 0
        )
        self.assertEqual(len(_ha_stubs.SCHEDULED.time_changes), 1)

    def test_shutdown_without_boundary_does_not_crash(self) -> None:
        """Line 245->exit: boundary unsubscribe is None."""
        coordinator = a_coordinator()
        coordinator.async_shutdown()
        self.assertIsNone(coordinator._boundary_unsubscribe)


class TestLedgerLookup(CoordinatorCase):
    def test_ledger_for_returns_none_for_none(self) -> None:
        coordinator = a_coordinator()
        self.assertIsNone(coordinator.ledger_for(None))

    def test_ledger_for_returns_none_for_unknown_qualified_name(self) -> None:
        coordinator = a_coordinator()
        self.assertIsNone(coordinator.ledger_for("not.a.rate"))


class TestNoResolution(CoordinatorCase):
    def test_refresh_when_no_period_resolves(self) -> None:
        """Lines 418-419: every period filtered out by day selection."""
        options = sample_options()
        options[CONST.CONF_DAY_PATTERNS][0][CONST.CONF_DAYS] = ["holiday"]
        coordinator = a_coordinator(options)
        coordinator.async_refresh()
        self.assertIsNone(coordinator.state.effective_rate)
        self.assertIn("no period resolves at this moment", coordinator.state.trace)


class TestExportAllowance(CoordinatorCase):
    def _export_capped(self) -> Any:
        options = sample_options()
        pattern = options[CONST.CONF_DAY_PATTERNS][0]
        pattern[CONST.CONF_EXPORT_SAME_ALL_DAY] = False
        pattern[CONST.CONF_EXPORT_PERIODS] = [
            {CONST.CONF_START: "00:00", CONST.CONF_END: "24:00", CONST.CONF_RATE: "Day"},
        ]
        pattern[CONST.CONF_EXPORT_RATES] = [
            {
                CONST.CONF_NAME: "Day",
                CONST.CONF_EXPORT_CENTS: 5.0,
                CONST.CONF_EXPORT_ALLOWANCE_KWH: 10.0,
                CONST.CONF_EXPORT_FALLBACK_CENTS: 1.0,
            }
        ]
        options[CONST.CONF_EXPORT_ENERGY_SENSOR] = "sensor.grid_export"
        coordinator = a_coordinator(options)
        coordinator.hass.states.set("sensor.grid_export", "0.0")
        coordinator._seed_retry_delay_seconds = 0
        run(coordinator._seed_energy_total())
        return coordinator

    def test_export_consumption_counts_against_allowance(self) -> None:
        """Lines 513-522: export allowance is decremented and exhausted."""
        coordinator = self._export_capped()
        coordinator.async_refresh()
        coordinator.hass.states.set("sensor.grid_export", "11.0")
        coordinator._accumulate_export_energy("sensor.grid_export")
        coordinator.async_refresh()
        self.assertTrue(coordinator.state.export_allowance_exhausted)
        self.assertAlmostEqual(
            coordinator.state.export_effective_price, 0.01
        )  # fallback 1 c/kWh


class TestDemandIntervalEdgeCases(CoordinatorCase):
    def test_instantaneous_demand_does_not_track_intervals(self) -> None:
        """Line 611: interval_key returns None for instantaneous demand."""
        options = sample_options()
        rate_in(options, 1)[CONST.CONF_DEMAND_PERIOD] = True
        rate_in(options, 1)[CONST.CONF_DEMAND_RATE] = 20.0
        rate_in(options, 1)[CONST.CONF_DEMAND_INTERVAL] = 0
        options[CONST.CONF_IMPORT_ENERGY_SENSOR] = "sensor.grid_import"
        coordinator = a_coordinator(options)
        coordinator.hass.states.set("sensor.grid_import", "0.0")
        coordinator._seed_retry_delay_seconds = 0
        run(coordinator._seed_energy_total())
        PKG.coordinator.dt_util.NOW = at(17)
        coordinator.async_refresh()
        ledger = coordinator.ledger_for(PKG.plan.qualified_name(
            coordinator.plan.name, "Every day", "Every day Peak"
        ))
        self.assertIsNone(ledger.interval_key)


class TestSupplyCharge(CoordinatorCase):
    def test_zero_supply_charge_short_circuits(self) -> None:
        """Lines 652-655: daily <= 0."""
        options = sample_options()
        options[CONST.CONF_SUPPLY_CHARGE_CENTS] = 0.0
        coordinator = a_coordinator(options)
        coordinator.async_refresh()
        self.assertEqual(coordinator.state.supply_charge_today, 0.0)
        self.assertEqual(coordinator.state.supply_charge_cycle, 0.0)
        self.assertEqual(coordinator.state.supply_charge_day, today())


class TestBoundaryScheduling(CoordinatorCase):
    def test_no_boundary_does_not_schedule(self) -> None:
        """Lines 680-681: no import and no export change found."""
        coordinator = a_coordinator()
        coordinator.state.next_change = None
        coordinator.state.next_export_change = None
        coordinator._schedule_next_boundary()
        self.assertEqual(len(_ha_stubs.SCHEDULED.points), 0)


class TestMeterSeeding(CoordinatorCase):
    def test_import_meter_seed_opens_gap_when_unreadable(self) -> None:
        """Line 702->711: import meter unreadable at startup."""
        options = sample_options()
        options[CONST.CONF_IMPORT_ENERGY_SENSOR] = "sensor.grid_import"
        coordinator = a_coordinator(options)
        coordinator._seed_retry_delay_seconds = 0
        run(coordinator._seed_energy_total())
        self.assertIsNone(coordinator._last_energy_total)
        self.assertIsNotNone(coordinator.state.gap_since)

    def test_export_meter_seed_opens_gap_when_unreadable(self) -> None:
        """Lines 712-718: export meter unreadable at startup."""
        options = sample_options()
        options[CONST.CONF_EXPORT_ENERGY_SENSOR] = "sensor.grid_export"
        coordinator = a_coordinator(options)
        coordinator._seed_retry_delay_seconds = 0
        run(coordinator._seed_energy_total())
        self.assertIsNone(coordinator._last_export_energy_total)
        self.assertIsNotNone(coordinator.state.gap_since)


class TestReadFloat(CoordinatorCase):
    def test_non_numeric_state_returns_none(self) -> None:
        """Lines 750-751: ValueError path."""
        coordinator = a_coordinator()
        coordinator.hass.states.set("sensor.weird", "not-a-number")
        self.assertIsNone(coordinator._read_float("sensor.weird"))


class TestStateChangeHandler(CoordinatorCase):
    def test_import_state_change_accumulates(self) -> None:
        """Lines 755-764: _handle_state_change routes to import and refreshes."""
        options = sample_options()
        options[CONST.CONF_IMPORT_ENERGY_SENSOR] = "sensor.grid_import"
        coordinator = a_coordinator(options)
        coordinator.hass.states.set("sensor.grid_import", "0.0")
        coordinator._seed_retry_delay_seconds = 0
        run(coordinator._seed_energy_total())
        coordinator.async_refresh()
        coordinator.hass.states.set("sensor.grid_import", "5.0")
        event = SimpleNamespace(data={"entity_id": "sensor.grid_import"})
        coordinator._handle_state_change(event)
        self.assertAlmostEqual(coordinator._last_energy_total, 5.0)

    def test_export_state_change_accumulates(self) -> None:
        options = sample_options()
        pattern = options[CONST.CONF_DAY_PATTERNS][0]
        pattern[CONST.CONF_EXPORT_SAME_ALL_DAY] = False
        pattern[CONST.CONF_EXPORT_PERIODS] = [
            {CONST.CONF_START: "00:00", CONST.CONF_END: "24:00", CONST.CONF_RATE: "Day"},
        ]
        pattern[CONST.CONF_EXPORT_RATES] = [
            {CONST.CONF_NAME: "Day", CONST.CONF_EXPORT_CENTS: 5.0}
        ]
        options[CONST.CONF_EXPORT_ENERGY_SENSOR] = "sensor.grid_export"
        coordinator = a_coordinator(options)
        coordinator.hass.states.set("sensor.grid_export", "0.0")
        coordinator._seed_retry_delay_seconds = 0
        run(coordinator._seed_energy_total())
        coordinator.async_refresh()
        coordinator.hass.states.set("sensor.grid_export", "3.0")
        event = SimpleNamespace(data={"entity_id": "sensor.grid_export"})
        coordinator._handle_state_change(event)
        self.assertAlmostEqual(coordinator._last_export_energy_total, 3.0)


class TestAccumulateEnergy(CoordinatorCase):
    def test_accumulate_with_no_resolution_records_reading(self) -> None:
        """Lines 805-806: nothing resolves, reading is still recorded."""
        options = sample_options()
        options[CONST.CONF_IMPORT_ENERGY_SENSOR] = "sensor.grid_import"
        coordinator = a_coordinator(options)
        coordinator.hass.states.set("sensor.grid_import", "0.0")
        coordinator._seed_retry_delay_seconds = 0
        run(coordinator._seed_energy_total())
        coordinator.state.resolution = None
        coordinator.hass.states.set("sensor.grid_import", "10.0")
        coordinator._accumulate_energy("sensor.grid_import")
        self.assertAlmostEqual(coordinator._last_energy_total, 10.0)


class TestGapManagement(CoordinatorCase):
    def test_close_gap_with_another_unreadable_input_keeps_gap_open(self) -> None:
        """Line 917->925: another input is still unreadable."""
        options = sample_options()
        options[CONST.CONF_IMPORT_ENERGY_SENSOR] = "sensor.grid_import"
        options[CONST.CONF_EXPORT_ENERGY_SENSOR] = "sensor.grid_export"
        coordinator = a_coordinator(options)
        coordinator.hass.states.set("sensor.grid_import", "0.0")
        coordinator.hass.states.set("sensor.grid_export", "0.0")
        coordinator._seed_retry_delay_seconds = 0
        run(coordinator._seed_energy_total())
        coordinator.async_refresh()
        coordinator._open_gap("sensor.grid_import", "import down")
        coordinator._open_gap("sensor.grid_export", "export down")
        coordinator._close_gap("sensor.grid_import")
        self.assertFalse(coordinator.state.data_complete)


class TestExpiredPlan(CoordinatorCase):
    def test_expired_issue_is_raised_only_once(self) -> None:
        """Line 945: _expired_warned short-circuit."""
        options = sample_options()
        options[CONST.CONF_VALID_TO] = "2026-01-01"
        coordinator = a_coordinator(options)
        module = sys.modules["homeassistant.helpers.issue_registry"]
        module.RAISED.clear()
        coordinator.async_refresh()
        coordinator.async_refresh()
        self.assertEqual(
            len([i for i, _ in module.RAISED if i == coordinator._expired_issue_id]), 1
        )


class TestHasSuccessor(CoordinatorCase):
    def test_no_meter_means_no_successor(self) -> None:
        """Line 975: no import sensor."""
        coordinator = a_coordinator()
        self.assertFalse(coordinator._has_successor(today()))

    def test_invalid_other_plan_is_skipped(self) -> None:
        """Lines 980-981: Plan.from_dict raises."""
        options = sample_options()
        options[CONST.CONF_IMPORT_ENERGY_SENSOR] = "sensor.grid_import"
        coordinator = a_coordinator(options)

        class BadEntry:
            entry_id = "entry2"
            title = "Bad"
            options: ClassVar[dict[str, Any]] = {
                CONST.CONF_IMPORT_ENERGY_SENSOR: "sensor.grid_import",
                CONST.CONF_VALID_FROM: "not-a-date",
            }

        coordinator.hass.config_entries.entries.append(BadEntry())
        self.assertFalse(coordinator._has_successor(today()))

    def test_successor_with_different_meter_is_ignored(self) -> None:
        """Line 976: different import sensor."""
        options = sample_options()
        options[CONST.CONF_IMPORT_ENERGY_SENSOR] = "sensor.grid_import"
        coordinator = a_coordinator(options)

        class OtherEntry:
            entry_id = "entry2"
            title = "Other"
            options: ClassVar[dict[str, Any]] = {
                CONST.CONF_IMPORT_ENERGY_SENSOR: "sensor.other_import"
            }

        coordinator.hass.config_entries.entries.append(OtherEntry())
        self.assertFalse(coordinator._has_successor(today()))


class TestTariffSelect(CoordinatorCase):
    def test_no_write_when_select_already_matches(self) -> None:
        """Line 1036: state.state == tariff."""
        options = sample_options()
        options[CONST.CONF_TARIFF_SELECTS] = ["select.meter_tariff"]
        coordinator = a_coordinator(options)
        off_peak = PKG.plan.qualified_name(
            coordinator.plan.name, "Every day", "Every day Off Peak"
        )
        coordinator.hass.states.set(
            "select.meter_tariff", off_peak, options=[off_peak]
        )
        coordinator.async_refresh()
        self.assertEqual(coordinator.hass.services.calls, [])


class TestTodayPeriods(CoordinatorCase):
    def test_today_periods_returns_rows(self) -> None:
        """Lines 1168-1191."""
        coordinator = a_coordinator()
        rows = coordinator.today_periods()
        self.assertEqual(len(rows), 2)
        self.assertIn("per_kwh", rows[0])
        self.assertIn("rate_name", rows[0])

    def test_today_periods_table_renders(self) -> None:
        """Lines 1202-1213."""
        coordinator = a_coordinator()
        table = coordinator.today_periods_table()
        self.assertIn("| Time | Rate | Price |", table)
        self.assertIn("c/kWh", table)

    def test_today_periods_table_empty_day(self) -> None:
        options = sample_options()
        options[CONST.CONF_DAY_PATTERNS][0][CONST.CONF_PERIODS] = []
        coordinator = a_coordinator(options)
        self.assertEqual(coordinator.today_periods_table(), "No periods today.")

    def test_problems_returns_validation_text(self) -> None:
        """Line 1218."""
        coordinator = a_coordinator()
        self.assertIsInstance(coordinator.problems, list)


if __name__ == "__main__":
    unittest.main()
