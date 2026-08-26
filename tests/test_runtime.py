"""The runtime half: coordinator, entities, and the options flow.

    python3 -m unittest tests.test_runtime

Same approach as the setup-flow tests: thin stubs for the Home Assistant APIs
these modules touch, then drive them. What is being tested is the component's
own logic — when it schedules, what it publishes, what it writes — not the
stubs.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import sys
import types
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
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
Rate = PKG.plan.Rate
ExportRate = PKG.plan.ExportRate
DayPattern = PKG.plan.DayPattern
Period = PKG.plan.Period
TariffCoordinator = PKG.coordinator.TariffCoordinator
OptionsFlow = PKG.config_flow.AbodePowerTariffsOptionsFlow

BRISBANE = ZoneInfo("Australia/Brisbane")
SYDNEY = ZoneInfo("Australia/Sydney")
ALL_DAYS = frozenset({"mon", "tue", "wed", "thu", "fri", "sat", "sun", "holiday"})
FORM = _ha_stubs.FlowResultType.FORM
MENU = _ha_stubs.FlowResultType.MENU
CREATE = _ha_stubs.FlowResultType.CREATE_ENTRY


def run(coro: Any) -> Any:
    return asyncio.run(coro)


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
        CONST.CONF_PRICES_INCLUDE_GST: True,
        CONST.CONF_GST_PERCENT: 10.0,
    }


def a_coordinator(options: dict[str, Any] | None = None) -> Any:
    hass = _ha_stubs.FakeHass()
    data = options or sample_options()
    plan = Plan.from_dict({**data, CONST.CONF_NAME: "Test"})
    return TariffCoordinator(hass, "entry1", plan, data)


def peak_name(coordinator: Any, timetable: str = "Every day") -> str:
    """Return the qualified identifier of the sample plan's Peak rate."""
    day_pattern = coordinator.plan.day_pattern_by_name(timetable)
    if day_pattern is not None:
        for rate in day_pattern.rates:
            if rate.name == "Every day Peak":
                return PKG.plan.qualified_name(
                    coordinator.plan.name, timetable, rate.name
                )
    raise AssertionError("no Peak rate on that timetable")


def rate_in(options: dict[str, Any], index: int, pattern: int = 0) -> dict[str, Any]:
    """Return one rate's own stored dict, nested inside its day pattern.

    A test-only navigation helper: rates moved off the plan and onto the
    day pattern that owns them (Gap #1), so a fixture that used to reach a
    stored rate with ``options[CONF_RATES][index]`` now has one more level
    to go through — the day pattern that nests it.
    """
    return options[CONST.CONF_DAY_PATTERNS][pattern][CONST.CONF_RATES][index]


class CoordinatorCase(unittest.TestCase):
    def setUp(self) -> None:
        _ha_stubs.SCHEDULED.__init__()  # type: ignore[misc]
        PKG.coordinator.dt_util.NOW = at(10)

    def tearDown(self) -> None:
        PKG.coordinator.dt_util.NOW = None


class TestResolution(CoordinatorCase):
    def test_the_rate_in_force(self) -> None:
        coordinator = a_coordinator()
        coordinator.async_refresh()
        assert coordinator.state.effective_rate is not None
        self.assertEqual(coordinator.state.effective_rate.name, "Every day Off Peak")

    def test_the_rate_changes_with_the_clock(self) -> None:
        coordinator = a_coordinator()
        PKG.coordinator.dt_util.NOW = at(17)
        coordinator.async_refresh()
        assert coordinator.state.effective_rate is not None
        self.assertEqual(coordinator.state.effective_rate.name, "Every day Peak")

    def test_export_price_comes_from_the_timetable(self) -> None:
        coordinator = a_coordinator()
        coordinator.async_refresh()
        self.assertAlmostEqual(coordinator.export_price_now(), 0.027)

    def test_a_trace_is_recorded(self) -> None:
        coordinator = a_coordinator()
        coordinator.async_refresh()
        self.assertTrue(coordinator.state.trace)


class TestScheduling(CoordinatorCase):
    def test_the_next_boundary_is_scheduled(self) -> None:
        coordinator = a_coordinator()
        coordinator.async_refresh()
        self.assertEqual(len(_ha_stubs.SCHEDULED.points), 1)
        moment, _ = _ha_stubs.SCHEDULED.points[0]
        self.assertEqual(moment.astimezone(BRISBANE).hour, 16)

    def test_the_previous_schedule_is_cancelled_before_the_next(self) -> None:
        coordinator = a_coordinator()
        coordinator.async_refresh()
        coordinator.async_refresh()
        self.assertEqual(_ha_stubs.SCHEDULED.cancelled, 1)
        self.assertEqual(len(_ha_stubs.SCHEDULED.points), 2)

    def test_a_minute_tick_is_registered_on_start(self) -> None:
        """On the zero second, so a tick lands on each whole-minute boundary.

        Nothing is then load-bearing: a wrong scheduled instant costs a minute
        rather than hours.
        """
        coordinator = a_coordinator()
        coordinator._seed_retry_delay_seconds = 0
        run(coordinator.async_start())
        ticks = [
            t
            for t in _ha_stubs.SCHEDULED.time_changes
            if t.get("second") == 0 and t.get("hour") is None
        ]
        self.assertEqual(len(ticks), 1)

    def test_midnight_is_no_longer_a_barrier(self) -> None:
        """The allowance belongs to the slot, so the calendar resets nothing."""
        coordinator = a_coordinator()
        coordinator._seed_retry_delay_seconds = 0
        run(coordinator.async_start())
        registered = [t for t in _ha_stubs.SCHEDULED.time_changes if t.get("hour") == 0]
        self.assertEqual(registered, [])
        self.assertFalse(hasattr(coordinator, "_handle_midnight"))

    def test_entities_are_told(self) -> None:
        coordinator = a_coordinator()
        coordinator.async_refresh()
        self.assertIn(f"{CONST.SIGNAL_UPDATE}_entry1", _ha_stubs.SCHEDULED.dispatched)

    def test_shutdown_releases_everything(self) -> None:
        coordinator = a_coordinator()
        coordinator._seed_retry_delay_seconds = 0
        run(coordinator.async_start())
        coordinator.async_shutdown()
        self.assertIsNone(coordinator._boundary_unsubscribe)


class TestExportScheduling(CoordinatorCase):
    """The import rate and the feed-in price are scheduled and reported apart."""

    EXPORT_PERIODS: ClassVar[list[dict[str, Any]]] = [
        {CONST.CONF_START: "00:00", CONST.CONF_END: "09:00", CONST.CONF_RATE: "Night"},
        {CONST.CONF_START: "09:00", CONST.CONF_END: "24:00", CONST.CONF_RATE: "Day"},
    ]
    EXPORT_RATES: ClassVar[list[dict[str, Any]]] = [
        {CONST.CONF_NAME: "Night", CONST.CONF_EXPORT_CENTS: 0.0},
        {CONST.CONF_NAME: "Day", CONST.CONF_EXPORT_CENTS: 5.0},
    ]

    def _with_timed_export(self, *, flat_import: bool) -> Any:
        data = sample_options()
        pattern = data[CONST.CONF_DAY_PATTERNS][0]
        if flat_import:
            pattern[CONST.CONF_PERIODS] = [
                {
                    CONST.CONF_START: "00:00",
                    CONST.CONF_END: "24:00",
                    CONST.CONF_RATE: "Every day Off Peak",
                },
            ]
        pattern[CONST.CONF_EXPORT_SAME_ALL_DAY] = False
        pattern[CONST.CONF_EXPORT_PERIODS] = list(self.EXPORT_PERIODS)
        data[CONST.CONF_EXPORT_RATES] = list(self.EXPORT_RATES)
        return a_coordinator(data)

    def test_it_wakes_at_the_feed_in_change_not_at_midnight(self) -> None:
        """The bug: a flat import rate meant nothing was scheduled all day."""
        PKG.coordinator.dt_util.NOW = at(8)
        coordinator = self._with_timed_export(flat_import=True)
        coordinator.async_refresh()
        self.assertEqual(len(_ha_stubs.SCHEDULED.points), 1)
        moment, _ = _ha_stubs.SCHEDULED.points[0]
        self.assertEqual(moment.astimezone(BRISBANE).hour, 9)

    def test_the_feed_in_change_is_reported(self) -> None:
        PKG.coordinator.dt_util.NOW = at(8)
        coordinator = self._with_timed_export(flat_import=True)
        coordinator.async_refresh()
        nxt = coordinator.state.next_export_change
        assert nxt is not None
        self.assertEqual(nxt.astimezone(BRISBANE).hour, 9)

    def test_the_import_change_is_reported_separately(self) -> None:
        PKG.coordinator.dt_util.NOW = at(8)
        coordinator = self._with_timed_export(flat_import=True)
        coordinator.async_refresh()
        nxt = coordinator.state.next_change
        assert nxt is not None
        self.assertEqual(nxt.astimezone(BRISBANE).date(), date(2026, 8, 15))

    def test_the_earlier_of_the_two_is_what_is_scheduled(self) -> None:
        """Import changes at 16:00, feed-in at 09:00. Wake at 09:00."""
        PKG.coordinator.dt_util.NOW = at(8)
        coordinator = self._with_timed_export(flat_import=False)
        coordinator.async_refresh()
        assert coordinator.state.next_change is not None
        assert coordinator.state.next_export_change is not None
        self.assertEqual(coordinator.state.next_change.astimezone(BRISBANE).hour, 16)
        self.assertEqual(
            coordinator.state.next_export_change.astimezone(BRISBANE).hour, 9
        )
        moment, _ = _ha_stubs.SCHEDULED.points[0]
        self.assertEqual(moment.astimezone(BRISBANE).hour, 9)

    def test_a_flat_feed_in_price_reports_nothing_and_changes_nothing(self) -> None:
        coordinator = a_coordinator()
        coordinator.async_refresh()
        self.assertIsNone(coordinator.state.next_export_change)
        moment, _ = _ha_stubs.SCHEDULED.points[0]
        self.assertEqual(moment.astimezone(BRISBANE).hour, 16)


class TestHolidays(CoordinatorCase):
    def _with_sensor(self) -> Any:
        options = sample_options()
        options[CONST.CONF_HOLIDAY_SENSOR] = "binary_sensor.workday"
        return a_coordinator(options)

    def test_no_sensor_means_no_holiday(self) -> None:
        self.assertFalse(a_coordinator().is_holiday(date(2026, 8, 14)))

    def test_workday_off_means_holiday(self) -> None:
        coordinator = self._with_sensor()
        coordinator.hass.states.set("binary_sensor.workday", "off")
        self.assertTrue(coordinator.is_holiday(PKG.coordinator.dt_util.NOW.date()))

    def test_workday_on_means_ordinary(self) -> None:
        coordinator = self._with_sensor()
        coordinator.hass.states.set("binary_sensor.workday", "on")
        self.assertFalse(coordinator.is_holiday(PKG.coordinator.dt_util.NOW.date()))

    def test_an_unavailable_sensor_falls_back_quietly(self) -> None:
        coordinator = self._with_sensor()
        coordinator.hass.states.set("binary_sensor.workday", "unavailable")
        self.assertFalse(coordinator.is_holiday(PKG.coordinator.dt_util.NOW.date()))
        self.assertTrue(coordinator._holiday_warned)
        # Second read must not warn again.
        coordinator.is_holiday(PKG.coordinator.dt_util.NOW.date())
        self.assertTrue(coordinator._holiday_warned)

    def test_only_today_can_be_answered(self) -> None:
        coordinator = self._with_sensor()
        coordinator.hass.states.set("binary_sensor.workday", "off")
        self.assertFalse(coordinator.is_holiday(date(2030, 1, 1)))


class TestStartupMeterRetries(CoordinatorCase):
    """The meter's own integration may not have loaded yet at startup.

    A gap opened for that reason alone would be a false alarm every single
    restart on a slower system, not a genuine data problem.
    """

    def test_production_defaults_are_three_attempts_five_seconds(self) -> None:
        """The actual values used when nothing overrides them for a test."""
        coordinator = a_coordinator()
        self.assertEqual(coordinator._seed_retry_attempts, 3)
        self.assertEqual(coordinator._seed_retry_delay_seconds, 5.0)

    def test_a_meter_that_becomes_readable_partway_through_is_used(self) -> None:
        """Succeeds on a later attempt, not just the first or none at all."""
        options = sample_options()
        options[CONST.CONF_IMPORT_ENERGY_SENSOR] = "sensor.grid_import"
        coordinator = a_coordinator(options)
        coordinator._seed_retry_delay_seconds = 0
        attempts_before_available = 2

        real_read_float = coordinator._read_float
        calls = {"count": 0}

        def flaky_read(entity_id: str) -> float | None:
            calls["count"] += 1
            if calls["count"] <= attempts_before_available:
                return None
            return real_read_float(entity_id)

        coordinator._read_float = flaky_read
        coordinator.hass.states.set("sensor.grid_import", "100.0")
        run(coordinator._seed_energy_total())

        self.assertEqual(calls["count"], attempts_before_available + 1)
        self.assertAlmostEqual(coordinator._last_energy_total, 100.0)
        self.assertIsNone(coordinator.state.gap_since)

    def test_a_meter_that_never_becomes_readable_still_opens_the_gap(self) -> None:
        """The retry does not silently swallow a genuine, ongoing problem."""
        options = sample_options()
        options[CONST.CONF_IMPORT_ENERGY_SENSOR] = "sensor.grid_import"
        coordinator = a_coordinator(options)
        coordinator._seed_retry_delay_seconds = 0
        # sensor.grid_import is never given a state at all.
        run(coordinator._seed_energy_total())
        self.assertIsNone(coordinator._last_energy_total)
        coordinator.async_refresh()
        self.assertIsNotNone(coordinator.state.gap_since)


class TestAllowanceAccounting(CoordinatorCase):
    def _capped(self) -> Any:
        options = sample_options()
        rate_in(options, 0)[CONST.CONF_RATE_ALLOWANCE_KWH] = 24.0
        rate_in(options, 0)[CONST.CONF_FALLBACK_RATE] = "Every day Peak"
        options[CONST.CONF_IMPORT_ENERGY_SENSOR] = "sensor.grid_import"
        coordinator = a_coordinator(options)
        coordinator.hass.states.set("sensor.grid_import", "100.0")
        coordinator._seed_retry_delay_seconds = 0
        run(coordinator._seed_energy_total())
        return coordinator

    def test_consumption_counts_against_the_allowance(self) -> None:
        coordinator = self._capped()
        coordinator.async_refresh()
        coordinator.hass.states.set("sensor.grid_import", "110.0")
        coordinator._accumulate_energy("sensor.grid_import")
        self.assertAlmostEqual(coordinator.state.allowance_used_kwh, 10.0)

    def test_past_the_allowance_the_fallback_rate_applies(self) -> None:
        coordinator = self._capped()
        coordinator.async_refresh()
        coordinator.hass.states.set("sensor.grid_import", "130.0")
        coordinator._accumulate_energy("sensor.grid_import")
        coordinator.async_refresh()
        assert coordinator.state.effective_rate is not None
        self.assertEqual(coordinator.state.effective_rate.name, "Every day Peak")
        self.assertTrue(coordinator.state.allowance_exhausted)

    def test_a_meter_reset_does_not_count(self) -> None:
        coordinator = self._capped()
        coordinator.async_refresh()
        coordinator.hass.states.set("sensor.grid_import", "5.0")
        coordinator._accumulate_energy("sensor.grid_import")
        self.assertEqual(coordinator.state.allowance_used_kwh, 0.0)

    def test_an_unavailable_meter_warns_once(self) -> None:
        coordinator = self._capped()
        coordinator.hass.states.set("sensor.grid_import", "unavailable")
        coordinator._accumulate_energy("sensor.grid_import")
        self.assertTrue(coordinator._energy_warned)

    def test_the_count_starts_again_in_a_new_slot_occurrence(self) -> None:
        """The allowance is the slot's. Tomorrow is a different occurrence.

        Nothing is carried between slots, days or billing cycles. A restart the
        morning after used to carry yesterday's figure until midnight.
        """
        coordinator = self._capped()
        PKG.coordinator.dt_util.NOW = at(9, 0, day=14)
        coordinator.async_refresh()
        coordinator.hass.states.set("sensor.grid_import", "110.0")
        coordinator._accumulate_energy("sensor.grid_import")
        self.assertAlmostEqual(coordinator.state.allowance_used_kwh, 10.0)
        first = coordinator.state.allowance_slot

        PKG.coordinator.dt_util.NOW = at(9, 0, day=15)
        coordinator.async_refresh()
        self.assertNotEqual(coordinator.state.allowance_slot, first)
        self.assertEqual(coordinator.state.allowance_used_kwh, 0.0)
        PKG.coordinator.dt_util.NOW = None

    def test_the_count_survives_within_one_slot_occurrence(self) -> None:
        """Recomputing inside the same slot must not zero a live count."""
        coordinator = self._capped()
        PKG.coordinator.dt_util.NOW = at(9, 0, day=14)
        coordinator.async_refresh()
        coordinator.hass.states.set("sensor.grid_import", "110.0")
        coordinator._accumulate_energy("sensor.grid_import")
        PKG.coordinator.dt_util.NOW = at(9, 1, day=14)
        coordinator.async_refresh()
        self.assertAlmostEqual(coordinator.state.allowance_used_kwh, 10.0)
        PKG.coordinator.dt_util.NOW = None

    def test_the_slot_names_the_period_not_just_the_rate(self) -> None:
        """Two periods naming one rate are two slots with an allowance each."""
        coordinator = self._capped()
        PKG.coordinator.dt_util.NOW = at(9, 0, day=14)
        coordinator.async_refresh()
        slot = coordinator.state.allowance_slot
        assert slot is not None
        resolution = coordinator.state.resolution
        assert resolution is not None
        self.assertIn(str(resolution.period.start), slot)
        self.assertIn(resolution.qualified_name, slot)
        PKG.coordinator.dt_util.NOW = None


class TestDemandAccumulation(CoordinatorCase):
    """Section 9 items 3, 5 and 9 — the demand side of P35."""

    def _demand(self, **rate_extra: Any) -> Any:
        opts = sample_options()
        rate_in(opts, 1)[CONST.CONF_DEMAND_PERIOD] = True
        rate_in(opts, 1)[CONST.CONF_DEMAND_RATE] = 20.0
        rate_in(opts, 1).update(rate_extra)
        opts[CONST.CONF_IMPORT_ENERGY_SENSOR] = "sensor.grid_import"
        coordinator = a_coordinator(opts)
        coordinator.hass.states.set("sensor.grid_import", "0.0")
        coordinator._seed_retry_delay_seconds = 0
        run(coordinator._seed_energy_total())
        return coordinator

    def test_energy_drawn_in_the_interval_becomes_the_peak_once_it_completes(
        self,
    ) -> None:
        """A5. Energy is credited to the rate it was drawn under, not thrown away."""
        coordinator = self._demand()
        PKG.coordinator.dt_util.NOW = at(17, 0, day=14)
        coordinator.async_refresh()
        coordinator.hass.states.set("sensor.grid_import", "2.5")
        coordinator._accumulate_energy("sensor.grid_import")

        # The interval closes when the clock moves into the next one.
        PKG.coordinator.dt_util.NOW = at(17, 30, day=14)
        coordinator.async_refresh()

        ledger = coordinator.ledger_for(peak_name(coordinator))
        self.assertAlmostEqual(ledger.peak_kw, 5.0, places=6)
        PKG.coordinator.dt_util.NOW = None

    def test_a_partial_interval_is_not_a_peak_candidate(self) -> None:
        coordinator = self._demand()
        PKG.coordinator.dt_util.NOW = at(17, 0, day=14)
        coordinator.async_refresh()
        coordinator.hass.states.set("sensor.grid_import", "2.5")
        coordinator._accumulate_energy("sensor.grid_import")
        # Still inside the same interval; nothing has completed yet.
        PKG.coordinator.dt_util.NOW = at(17, 15, day=14)
        coordinator.async_refresh()
        ledger = coordinator.ledger_for(peak_name(coordinator))
        self.assertEqual(ledger.peak_kw, 0.0)
        PKG.coordinator.dt_util.NOW = None

    def test_leaving_the_rate_discards_a_part_finished_interval(self) -> None:
        """Consumption never billed under this rate cannot set its peak."""
        coordinator = self._demand()
        PKG.coordinator.dt_util.NOW = at(15, 45, day=14)
        coordinator.async_refresh()  # Off Peak, not the demand rate.
        coordinator.hass.states.set("sensor.grid_import", "1.0")
        coordinator._accumulate_energy("sensor.grid_import")

        # 16:00 crosses into Peak, which does carry a demand charge.
        PKG.coordinator.dt_util.NOW = at(16, 5, day=14)
        coordinator.async_refresh()
        ledger = coordinator.ledger_for(peak_name(coordinator))
        self.assertEqual(ledger.interval_kwh, 0.0)
        PKG.coordinator.dt_util.NOW = None

    def test_two_rates_on_two_timetables_keep_separate_peaks(self) -> None:
        """The strip.py failure, asserted in the new place it could recur."""
        opts = {
            CONST.CONF_DAY_PATTERNS: [
                {
                    CONST.CONF_NAME: "Weekday",
                    CONST.CONF_DAYS: ["mon", "tue", "wed", "thu", "fri"],
                    CONST.CONF_RATES: [
                        {
                            CONST.CONF_NAME: "Every day Peak",
                            CONST.CONF_IMPORT_CENTS: 56.88,
                            CONST.CONF_DEMAND_PERIOD: True,
                            CONST.CONF_DEMAND_RATE: 20.0,
                        }
                    ],
                    CONST.CONF_PERIODS: [
                        {
                            CONST.CONF_START: "00:00",
                            CONST.CONF_END: "24:00",
                            CONST.CONF_RATE: "Every day Peak",
                        }
                    ],
                },
                {
                    CONST.CONF_NAME: "Weekend",
                    CONST.CONF_DAYS: ["sat", "sun", "holiday"],
                    CONST.CONF_RATES: [
                        {
                            CONST.CONF_NAME: "Every day Peak",
                            CONST.CONF_IMPORT_CENTS: 40.0,
                            CONST.CONF_DEMAND_PERIOD: True,
                            CONST.CONF_DEMAND_RATE: 20.0,
                        }
                    ],
                    CONST.CONF_PERIODS: [
                        {
                            CONST.CONF_START: "00:00",
                            CONST.CONF_END: "24:00",
                            CONST.CONF_RATE: "Every day Peak",
                        }
                    ],
                },
            ],
            CONST.CONF_IMPORT_ENERGY_SENSOR: "sensor.grid_import",
        }
        coordinator = a_coordinator(opts)
        coordinator.hass.states.set("sensor.grid_import", "0.0")
        coordinator._seed_retry_delay_seconds = 0
        run(coordinator._seed_energy_total())

        weekday_ledger = coordinator.ledger_for(peak_name(coordinator, "Weekday"))
        weekend_ledger = coordinator.ledger_for(peak_name(coordinator, "Weekend"))
        weekday_ledger.peak_kw = 5.0
        weekend_ledger.peak_kw = 1.0
        self.assertNotEqual(weekday_ledger.peak_kw, weekend_ledger.peak_kw)
        self.assertIsNot(weekday_ledger, weekend_ledger)

    def test_the_two_bases_cost_different_money_from_the_same_peak(self) -> None:
        flat = self._demand(demand_basis="period")
        per_day = self._demand(demand_basis="day")
        for coordinator in (flat, per_day):
            PKG.coordinator.dt_util.NOW = at(10, 0, day=14)
            coordinator.async_refresh()
            ledger = coordinator.ledger_for(peak_name(coordinator))
            ledger.peak_kw = 5.0
        flat_cost = PKG.accounting.demand_cost(5.0, 0.20, "period", 31)
        per_day_cost = PKG.accounting.demand_cost(5.0, 0.20, "day", 31)
        self.assertAlmostEqual(flat_cost, 1.00, places=6)
        self.assertAlmostEqual(per_day_cost, 31.00, places=6)
        PKG.coordinator.dt_util.NOW = None

    def test_a_restored_peak_from_a_different_cycle_is_discarded(self) -> None:
        """Consistent with the allowance restore: identity is the cycle key."""
        coordinator = self._demand()
        PKG.coordinator.dt_util.NOW = at(17, 0, day=14)
        coordinator.async_refresh()
        ledger = coordinator.ledger_for(peak_name(coordinator))
        ledger.peak_kw = 9.0
        ledger.peak_cycle = "2020-01-01"
        # A refresh recomputes the cycle key and rolls anything stale.
        coordinator.async_refresh()
        self.assertEqual(ledger.peak_kw, 0.0)
        PKG.coordinator.dt_util.NOW = None


class TestBillingCycle(CoordinatorCase):
    """Rule 11, reinstated: the supply charge accumulates."""

    def test_the_supply_charge_lands_in_full_at_midnight(self) -> None:
        """Gap #5: the full charge lands the moment the day begins, no proration."""
        coordinator = a_coordinator()
        PKG.coordinator.dt_util.NOW = at(0, 0, day=14)
        coordinator.async_refresh()
        self.assertAlmostEqual(coordinator.state.supply_charge_today, 1.166, places=3)
        # Still the same figure at noon: it does not grow across the day.
        PKG.coordinator.dt_util.NOW = at(12, 0, day=14)
        coordinator.async_refresh()
        self.assertAlmostEqual(coordinator.state.supply_charge_today, 1.166, places=3)
        PKG.coordinator.dt_util.NOW = None

    def test_the_cycle_accrual_adds_the_closed_days(self) -> None:
        options = sample_options()
        options[CONST.CONF_BILLING_CYCLE_DAY] = 12
        coordinator = a_coordinator(options)
        PKG.coordinator.dt_util.NOW = at(0, 0, day=14)  # third day of the cycle
        coordinator.async_refresh()
        # Three whole days landed this cycle (the 12th, 13th, 14th) — today's
        # own charge lands in full the moment today begins (Gap #5), not
        # partway through it.
        self.assertAlmostEqual(
            coordinator.state.supply_charge_cycle, 1.166 * 3, places=3
        )
        PKG.coordinator.dt_util.NOW = None

    def test_a_new_billing_cycle_clears_every_ledgers_peak(self) -> None:
        options = sample_options()
        options[CONST.CONF_BILLING_CYCLE_DAY] = 12
        rate_in(options, 1)[CONST.CONF_DEMAND_PERIOD] = True
        rate_in(options, 1)[CONST.CONF_DEMAND_RATE] = 20.0
        options[CONST.CONF_IMPORT_ENERGY_SENSOR] = "sensor.grid_import"
        coordinator = a_coordinator(options)
        PKG.coordinator.dt_util.NOW = at(17, 0, day=14)  # inside the Aug 12 cycle
        coordinator.async_refresh()
        ledger = coordinator.ledger_for(peak_name(coordinator))
        ledger.peak_kw = 5.0

        # September 12 opens the next cycle.
        PKG.coordinator.dt_util.NOW = datetime(2026, 9, 12, 17, 0, tzinfo=BRISBANE)
        coordinator.async_refresh()
        self.assertEqual(ledger.peak_kw, 0.0)
        PKG.coordinator.dt_util.NOW = None


class TestGapDetection(CoordinatorCase):
    """Section 6. A gap is any interruption to an input."""

    def _capped_with_meter(self) -> Any:
        options = sample_options()
        rate_in(options, 0)[CONST.CONF_RATE_ALLOWANCE_KWH] = 24.0
        rate_in(options, 0)[CONST.CONF_FALLBACK_RATE] = "Every day Peak"
        options[CONST.CONF_IMPORT_ENERGY_SENSOR] = "sensor.grid_import"
        coordinator = a_coordinator(options)
        coordinator.hass.states.set("sensor.grid_import", "100.0")
        coordinator._seed_retry_delay_seconds = 0
        run(coordinator._seed_energy_total())
        return coordinator

    def test_an_unavailable_meter_opens_the_gap_immediately(self) -> None:
        coordinator = self._capped_with_meter()
        coordinator.async_refresh()
        coordinator.hass.states.set("sensor.grid_import", "unavailable")
        coordinator._accumulate_energy("sensor.grid_import")
        self.assertFalse(coordinator.state.data_complete)
        self.assertFalse(coordinator.state.cycle_complete)

    def test_a_gap_raises_a_repair_issue(self) -> None:
        coordinator = self._capped_with_meter()
        coordinator.async_refresh()
        module = sys.modules["homeassistant.helpers.issue_registry"]
        module.RAISED.clear()
        coordinator.hass.states.set("sensor.grid_import", "unavailable")
        coordinator._accumulate_energy("sensor.grid_import")
        self.assertEqual(len(module.RAISED), 1)
        issue_id, _ = module.RAISED[0]
        self.assertEqual(issue_id, coordinator._gap_issue_id)

    def test_recovery_clears_the_repair_issue(self) -> None:
        coordinator = self._capped_with_meter()
        coordinator.async_refresh()
        module = sys.modules["homeassistant.helpers.issue_registry"]
        module.DELETED.clear()
        coordinator.hass.states.set("sensor.grid_import", "unavailable")
        coordinator._accumulate_energy("sensor.grid_import")
        coordinator.hass.states.set("sensor.grid_import", "105.0")
        coordinator._accumulate_energy("sensor.grid_import")
        self.assertIn(coordinator._gap_issue_id, module.DELETED)

    def test_a_second_gap_does_not_raise_the_issue_twice(self) -> None:
        """The immediate flag is a level, not an edge; raising is idempotent."""
        coordinator = self._capped_with_meter()
        coordinator.async_refresh()
        module = sys.modules["homeassistant.helpers.issue_registry"]
        module.RAISED.clear()
        coordinator.hass.states.set("sensor.grid_import", "unavailable")
        coordinator._accumulate_energy("sensor.grid_import")
        coordinator._accumulate_energy("sensor.grid_import")
        self.assertEqual(len(module.RAISED), 1)

    def test_recovery_clears_the_immediate_flag_but_not_the_cycle_flag(self) -> None:
        coordinator = self._capped_with_meter()
        coordinator.async_refresh()
        coordinator.hass.states.set("sensor.grid_import", "unavailable")
        coordinator._accumulate_energy("sensor.grid_import")
        coordinator.hass.states.set("sensor.grid_import", "105.0")
        coordinator._accumulate_energy("sensor.grid_import")
        self.assertTrue(coordinator.state.data_complete)
        self.assertFalse(coordinator.state.cycle_complete)

    def test_the_cycle_flag_clears_only_when_the_cycle_rolls(self) -> None:
        coordinator = self._capped_with_meter()
        PKG.coordinator.dt_util.NOW = at(9, 0, day=14)
        coordinator.async_refresh()
        coordinator.hass.states.set("sensor.grid_import", "unavailable")
        coordinator._accumulate_energy("sensor.grid_import")
        self.assertFalse(coordinator.state.cycle_complete)

        # Still the same cycle tomorrow (billing day defaults to the 1st).
        PKG.coordinator.dt_util.NOW = at(9, 0, day=15)
        coordinator.async_refresh()
        self.assertFalse(coordinator.state.cycle_complete)
        PKG.coordinator.dt_util.NOW = None

    def test_every_ledgers_incomplete_flag_is_set_by_a_gap(self) -> None:
        options = sample_options()
        rate_in(options, 1)[CONST.CONF_DEMAND_PERIOD] = True
        rate_in(options, 1)[CONST.CONF_DEMAND_RATE] = 20.0
        options[CONST.CONF_IMPORT_ENERGY_SENSOR] = "sensor.grid_import"
        coordinator = a_coordinator(options)
        coordinator.hass.states.set("sensor.grid_import", "0.0")
        coordinator._seed_retry_delay_seconds = 0
        run(coordinator._seed_energy_total())
        PKG.coordinator.dt_util.NOW = at(17, 0, day=14)
        coordinator.async_refresh()
        coordinator.hass.states.set("sensor.grid_import", "unavailable")
        coordinator._accumulate_energy("sensor.grid_import")
        ledger = coordinator.ledger_for(peak_name(coordinator))
        self.assertTrue(ledger.incomplete)
        PKG.coordinator.dt_util.NOW = None


class TestForwardSeriesIsHeld(CoordinatorCase):
    """The price sensors ask for the forecast every time they write state.

    With an energy meter attached that is several times a minute, and the
    series only actually changes on the resolution grid.
    """

    def test_the_same_slot_reuses_the_series(self) -> None:
        coordinator = a_coordinator()
        self.assertIs(
            coordinator.forward_intervals(24, 30), coordinator.forward_intervals(24, 30)
        )

    def test_a_new_slot_rebuilds_it(self) -> None:
        coordinator = a_coordinator()
        first = coordinator.forward_intervals(24, 30)
        PKG.coordinator.dt_util.NOW = at(10, 30)
        self.assertIsNot(first, coordinator.forward_intervals(24, 30))

    def test_a_moment_later_in_the_same_slot_does_not(self) -> None:
        coordinator = a_coordinator()
        first = coordinator.forward_intervals(24, 30)
        PKG.coordinator.dt_util.NOW = at(10, 29)
        self.assertIs(first, coordinator.forward_intervals(24, 30))

    def test_a_different_request_is_not_confused_with_it(self) -> None:
        coordinator = a_coordinator()
        day = coordinator.forward_intervals(24, 30)
        hour = coordinator.forward_intervals(1, 60)
        self.assertIsNot(day, hour)
        self.assertEqual(len(hour), 1)

    def test_a_reload_rebuilds_it(self) -> None:
        """A7: apply_plan was dead in production — a reload replaces the whole
        coordinator, which is what actually resets this cache, not a method
        called on a live instance.
        """
        coordinator = a_coordinator()
        first = coordinator.forward_intervals(24, 30)
        reloaded = a_coordinator()
        self.assertIsNot(first, reloaded.forward_intervals(24, 30))


class TestForwardSeriesAcrossTheFallBack(CoordinatorCase):
    """P26: the cache key must tell the two passes of a repeated hour apart.

    P25 fixed ``intervals.generate`` itself. This is the coupled defect one
    level up: the cache key that decides whether to call it again is entirely
    wall clock, so a series built during the first 2am on the fall-back
    morning is handed back unchanged during the second 2am, because nothing
    in the key differs.
    """

    def setUp(self) -> None:
        super().setUp()
        self._real_zone = PKG.coordinator.dt_util.DEFAULT_ZONE
        PKG.coordinator.dt_util.DEFAULT_ZONE = SYDNEY

    def tearDown(self) -> None:
        PKG.coordinator.dt_util.DEFAULT_ZONE = self._real_zone
        super().tearDown()

    def test_the_second_pass_forces_a_rebuild(self) -> None:
        coordinator = a_coordinator()
        PKG.coordinator.dt_util.NOW = datetime(2026, 4, 5, 2, 15, tzinfo=SYDNEY, fold=0)
        first = coordinator.forward_intervals(24, 30)
        PKG.coordinator.dt_util.NOW = datetime(2026, 4, 5, 2, 15, tzinfo=SYDNEY, fold=1)
        second = coordinator.forward_intervals(24, 30)
        self.assertIsNot(first, second)

    def test_the_rebuilt_series_starts_an_hour_later_in_real_time(self) -> None:
        """Not just a different object — the correct, later instant."""
        coordinator = a_coordinator()
        PKG.coordinator.dt_util.NOW = datetime(2026, 4, 5, 2, 15, tzinfo=SYDNEY, fold=0)
        first = coordinator.forward_intervals(24, 30)
        PKG.coordinator.dt_util.NOW = datetime(2026, 4, 5, 2, 15, tzinfo=SYDNEY, fold=1)
        second = coordinator.forward_intervals(24, 30)
        self.assertEqual(
            second[0].start.astimezone(UTC) - first[0].start.astimezone(UTC),
            timedelta(hours=1),
        )

    def test_the_first_pass_alone_is_unaffected(self) -> None:
        """Asking twice inside the first pass must still reuse the series."""
        coordinator = a_coordinator()
        PKG.coordinator.dt_util.NOW = datetime(2026, 4, 5, 2, 15, tzinfo=SYDNEY, fold=0)
        first = coordinator.forward_intervals(24, 30)
        self.assertIs(first, coordinator.forward_intervals(24, 30))


class TestTheTraceHoldsStill(CoordinatorCase):
    """The trace is published as a sensor attribute.

    A live figure in it rewrites the attribute, and the entity state with it,
    on every meter reading. How much allowance is left has its own sensor.
    """

    def _capped(self) -> Any:
        data = sample_options()
        rate_in(data, 0)[CONST.CONF_RATE_ALLOWANCE_KWH] = 24.0
        rate_in(data, 0)[CONST.CONF_FALLBACK_RATE] = "Every day Peak"
        data[CONST.CONF_IMPORT_ENERGY_SENSOR] = "sensor.grid_import"
        coordinator = a_coordinator(data)
        coordinator.hass.states.set("sensor.grid_import", "100.0")
        coordinator._seed_retry_delay_seconds = 0
        run(coordinator._seed_energy_total())
        return coordinator

    def _consume(self, coordinator: Any, total: str) -> None:
        coordinator.hass.states.set("sensor.grid_import", total)
        coordinator._accumulate_energy("sensor.grid_import")
        coordinator.async_refresh()

    def test_it_does_not_move_as_the_meter_ticks(self) -> None:
        coordinator = self._capped()
        coordinator.async_refresh()
        before = coordinator.state.trace
        self._consume(coordinator, "105.0")
        self.assertEqual(coordinator.state.trace, before)
        self._consume(coordinator, "110.0")
        self.assertEqual(coordinator.state.trace, before)

    def test_within_the_allowance_it_says_so_and_no_more(self) -> None:
        coordinator = self._capped()
        coordinator.async_refresh()
        self.assertEqual(
            coordinator.state.trace, ("day set Every day", "within the allowance")
        )

    def test_it_still_reports_the_allowance_being_spent(self) -> None:
        coordinator = self._capped()
        coordinator.async_refresh()
        self._consume(coordinator, "130.0")
        self.assertEqual(
            coordinator.state.trace,
            ("day set Every day", "allowance spent", "priced at Every day Peak"),
        )

    def test_the_remaining_figure_is_still_published_by_its_own_sensor(self) -> None:
        coordinator = self._capped()
        coordinator.async_refresh()
        self._consume(coordinator, "110.0")
        self.assertAlmostEqual(coordinator.state.allowance_remaining_kwh, 14.0)


class TestTheOneWrite(CoordinatorCase):
    def _linked(self, options_extra: dict[str, Any] | None = None) -> Any:
        options = sample_options()
        options[CONST.CONF_TARIFF_SELECTS] = ["select.meter_tariff"]
        options.update(options_extra or {})
        return a_coordinator(options)

    def test_nothing_is_written_when_no_select_is_nominated(self) -> None:
        coordinator = a_coordinator()
        coordinator.async_refresh()
        self.assertEqual(coordinator.hass.services.calls, [])

    def test_the_select_is_set_to_the_rate_in_force(self) -> None:
        coordinator = self._linked()
        off_peak = peak_name(coordinator).replace(
            "import.every_day_peak", "import.every_day_off_peak"
        )
        peak = peak_name(coordinator)
        coordinator.hass.states.set(
            "select.meter_tariff",
            peak,
            options=[off_peak, peak],
        )
        coordinator.async_refresh()
        self.assertEqual(
            coordinator.hass.services.calls,
            [
                (
                    "select",
                    "select_option",
                    {
                        "entity_id": "select.meter_tariff",
                        "option": off_peak,
                    },
                )
            ],
        )

    def test_it_is_not_written_twice_for_the_same_rate(self) -> None:
        coordinator = self._linked()
        off_peak = peak_name(coordinator).replace(
            "import.every_day_peak", "import.every_day_off_peak"
        )
        peak = peak_name(coordinator)
        coordinator.hass.states.set(
            "select.meter_tariff",
            peak,
            options=[off_peak, peak],
        )
        coordinator.async_refresh()
        coordinator.async_refresh()
        self.assertEqual(len(coordinator.hass.services.calls), 1)

    def test_a_missing_option_is_refused_not_forced(self) -> None:
        coordinator = self._linked()
        coordinator.hass.states.set(
            "select.meter_tariff", "peak", options=["peak", "offpeak"]
        )
        coordinator.async_refresh()
        self.assertEqual(coordinator.hass.services.calls, [])

    def test_a_missing_select_is_survived(self) -> None:
        coordinator = self._linked()
        coordinator.async_refresh()
        self.assertEqual(coordinator.hass.services.calls, [])


class TestExpiredPlan(CoordinatorCase):
    def test_an_expired_plan_is_held_not_dropped(self) -> None:
        options = sample_options()
        options[CONST.CONF_VALID_TO] = "2026-01-01"
        coordinator = a_coordinator(options)
        coordinator.async_refresh()
        self.assertTrue(coordinator.state.plan_expired)
        self.assertIsNotNone(coordinator.state.effective_rate)


class TestForwardIntervals(CoordinatorCase):
    def test_the_series_covers_the_horizon(self) -> None:
        coordinator = a_coordinator()
        series = coordinator.forward_intervals(6, 30)
        self.assertEqual(len(series), 12)
        self.assertEqual(
            series[0].rate,
            peak_name(coordinator).replace(
                "import.every_day_peak", "import.every_day_off_peak"
            ),
        )

    def test_the_service_shape(self) -> None:
        coordinator = a_coordinator()
        payload = coordinator.forward_intervals(1, 60)[0].as_dict()
        self.assertEqual(payload["duration"], 60)
        self.assertIn("per_kwh", payload)
        self.assertFalse(payload["forecast"])


class TestEntityBase(CoordinatorCase):
    def test_available_only_when_a_period_resolves(self) -> None:
        coordinator = a_coordinator()
        entity = PKG.entity.TariffEntity(coordinator, "import_price")
        self.assertFalse(entity.available)
        coordinator.async_refresh()
        self.assertTrue(entity.available)

    def test_unique_id_and_device(self) -> None:
        coordinator = a_coordinator()
        entity = PKG.entity.TariffEntity(coordinator, "import_price")
        self.assertEqual(entity._attr_unique_id, "entry1_import_price")
        self.assertEqual(coordinator.device_identifier, (CONST.DOMAIN, "entry1"))

    def test_names_come_from_translations(self) -> None:
        coordinator = a_coordinator()
        entity = PKG.entity.TariffEntity(coordinator, "import_price")
        self.assertTrue(entity._attr_has_entity_name)
        self.assertEqual(entity._attr_translation_key, "import_price")


class FakeEntry:
    """The parts of ConfigEntry the options flow reads."""

    def __init__(self, options: dict[str, Any]) -> None:
        self.options = options
        self.title = "Test Plan"
        self.entry_id = "entry1"


class OptionsDriver:
    def __init__(self, options: dict[str, Any] | None = None) -> None:
        self.flow = OptionsFlow()
        self.flow.config_entry = FakeEntry(options or sample_options())
        self.flow.hass = _ha_stubs.FakeHass()
        self.result: dict[str, Any] = {}

    def start(self) -> dict[str, Any]:
        self.result = run(self.flow.async_step_init())
        return self.result

    def choose(self, option: str) -> dict[str, Any]:
        assert self.result["type"] == MENU, self.result
        assert option in self.result["menu_options"], self.result["menu_options"]
        self.result = run(getattr(self.flow, f"async_step_{option}")())
        return self.result

    def submit(self, **overrides: Any) -> dict[str, Any]:
        assert self.result["type"] == FORM, self.result
        payload = _ha_stubs.defaults(self.result)
        payload.update(overrides)
        step = getattr(self.flow, f"async_step_{self.result['step_id']}")
        self.result = run(step(payload))
        return self.result

    @property
    def step(self) -> str:
        return str(self.result.get("step_id", self.result.get("type")))


class TestOptionsFlow(unittest.TestCase):
    def test_the_menu_shows_the_plan(self) -> None:
        driver = OptionsDriver()
        result = driver.start()
        self.assertEqual(result["type"], MENU)
        plan_text = result["description_placeholders"]["plan"]
        self.assertIn("Every day", plan_text)
        self.assertIn("Coverage: complete", plan_text)

    def test_every_menu_entry_opens(self) -> None:
        for entry in PKG.config_flow.MENU:
            if entry == "save":
                continue
            driver = OptionsDriver()
            driver.start()
            result = driver.choose(entry)
            self.assertIn(result["type"], (FORM, MENU), entry)

    def test_save_writes_a_valid_plan(self) -> None:
        driver = OptionsDriver()
        driver.start()
        result = driver.choose("save")
        self.assertEqual(result["type"], CREATE)
        plan = Plan.from_dict({**result["data"], CONST.CONF_NAME: "Test Plan"})
        self.assertEqual(PKG.validate.validate_plan(plan), [])

    def test_save_is_refused_while_the_plan_is_invalid(self) -> None:
        options = sample_options()
        options[CONST.CONF_DAY_PATTERNS][0][CONST.CONF_PERIODS].pop()
        driver = OptionsDriver(options)
        driver.start()
        result = driver.choose("save")
        self.assertEqual(result["type"], MENU)
        self.assertIn("Not ready to save", result["description_placeholders"]["plan"])

    def test_adding_a_rate(self) -> None:
        driver = OptionsDriver()
        driver.start()
        driver.choose("rates_menu")
        driver.choose("rate_add")
        driver.submit(name="Shoulder", import_cents=32.1)
        self.assertEqual(driver.step, "rates_menu")
        self.assertIn("Shoulder", driver.result["description_placeholders"]["rates"])

    def test_renaming_a_rate_follows_into_its_periods(self) -> None:
        driver = OptionsDriver()
        driver.start()
        driver.choose("rates_menu")
        driver.choose("rate_pick")
        driver.submit(name="test_plan.every_day.import.every_day_peak")
        driver.submit(name="Every day Evening", import_cents=56.88)
        periods = driver.flow.working[CONST.CONF_DAY_PATTERNS][0][CONST.CONF_PERIODS]
        self.assertEqual(periods[1][CONST.CONF_RATE], "Every day Evening")

    def test_a_rate_in_use_cannot_be_removed(self) -> None:
        driver = OptionsDriver()
        driver.start()
        driver.choose("rates_menu")
        driver.choose("rate_remove")
        driver.submit(name="test_plan.every_day.import.every_day_peak")
        self.assertEqual(driver.result["errors"].get("name"), "rate_in_use")

    def test_duplicating_a_timetable_copies_its_periods(self) -> None:
        driver = OptionsDriver()
        driver.start()
        driver.choose("day_patterns_menu")
        driver.choose("day_pattern_duplicate")
        result = driver.submit(source="Every day", name="Weekend")
        # Nothing is created yet — day coverage is asked for first, same as
        # a genuine add, not copied from the source (A1c: copying it
        # verbatim produced two patterns that silently collided).
        self.assertEqual(result["step_id"], "day_pattern_add")
        self.assertEqual(len(driver.flow.working[CONST.CONF_DAY_PATTERNS]), 1)
        driver.submit(
            name="Weekend", same_every_day=False, days=["sat", "sun", "holiday"]
        )
        patterns = driver.flow.working[CONST.CONF_DAY_PATTERNS]
        self.assertEqual(len(patterns), 2)
        self.assertEqual(patterns[1][CONST.CONF_NAME], "Weekend")
        self.assertEqual(set(patterns[1][CONST.CONF_DAYS]), {"sat", "sun", "holiday"})
        self.assertEqual(len(patterns[1][CONST.CONF_PERIODS]), 2)

    def test_editing_a_period(self) -> None:
        driver = OptionsDriver()
        driver.start()
        driver.choose("periods_pick_day_pattern")
        self.assertEqual(driver.step, "periods_menu")
        driver.choose("period_pick")
        driver.submit(period="00:00 to 16:00  Every day Off Peak")
        driver.submit(start="00:00:00", end="15:00:00", rate="Every day Off Peak")
        self.assertEqual(driver.step, "periods_menu")
        periods = driver.flow.working[CONST.CONF_DAY_PATTERNS][0][CONST.CONF_PERIODS]
        self.assertEqual(periods[0][CONST.CONF_END], "15:00")

    def test_the_feed_in_section_opens(self) -> None:
        driver = OptionsDriver()
        driver.start()
        result = driver.choose("export_menu")
        self.assertEqual(result["type"], MENU)

    def test_the_rate_plan_card_renders(self) -> None:
        driver = OptionsDriver()
        driver.start()
        result = driver.choose("rate_plan_card")
        card = result["description_placeholders"]["card"]
        self.assertIn("buy", card)
        self.assertIn("test_plan.every_day.import.every_day_peak", card)

    def test_a_failing_step_shows_the_traceback(self) -> None:
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        driver = OptionsDriver()
        driver.flow._working = None
        driver.flow.config_entry.options = {"rates": [{"import_cents": 1}]}
        result = run(driver.flow.async_step_rate_plan_card())
        self.assertIn(result["step_id"], ("rate_plan_card", "failure"))


if __name__ == "__main__":
    unittest.main()


class TestOptionsFlowBranches(unittest.TestCase):
    """The paths a first pass misses: empty lists, removals, redirects."""

    def _empty(self) -> OptionsDriver:
        return OptionsDriver({CONST.CONF_RATES: [], CONST.CONF_DAY_PATTERNS: []})

    def test_editing_a_rate_with_none_defined_opens_the_add_form(self) -> None:
        driver = self._empty()
        driver.start()
        driver.choose("rates_menu")
        self.assertEqual(driver.choose("rate_pick")["step_id"], "rate_add")

    def test_removing_a_rate_with_none_defined_returns_to_the_menu(self) -> None:
        driver = self._empty()
        driver.start()
        driver.choose("rates_menu")
        self.assertEqual(driver.choose("rate_remove")["step_id"], "rates_menu")

    def test_removing_an_unused_rate(self) -> None:
        driver = OptionsDriver()
        driver.start()
        driver.choose("rates_menu")
        driver.choose("rate_add")
        driver.submit(name="Spare", import_cents=1.0)
        driver.choose("rate_remove")
        driver.submit(name="test_plan.every_day.import.spare")
        self.assertEqual(driver.step, "rates_menu")
        self.assertNotIn("Spare", driver.result["description_placeholders"]["rates"])

    def test_timetables_with_none_defined_open_the_add_form(self) -> None:
        driver = self._empty()
        driver.start()
        driver.choose("day_patterns_menu")
        self.assertEqual(
            driver.choose("day_pattern_pick")["step_id"], "day_pattern_add"
        )
        driver.start()
        driver.choose("day_patterns_menu")
        self.assertEqual(
            driver.choose("day_pattern_duplicate")["step_id"], "day_pattern_add"
        )

    def test_adding_and_removing_a_timetable(self) -> None:
        driver = OptionsDriver()
        driver.start()
        driver.choose("day_patterns_menu")
        driver.choose("day_pattern_add")
        driver.submit(name="Weekend", same_every_day=False, days=["sat", "sun"])
        self.assertEqual(driver.step, "day_patterns_menu")
        driver.choose("day_pattern_remove")
        driver.submit(name="Weekend")
        self.assertEqual(len(driver.flow.working[CONST.CONF_DAY_PATTERNS]), 1)

    def test_a_timetable_needs_a_name_and_days(self) -> None:
        driver = OptionsDriver()
        driver.start()
        driver.choose("day_patterns_menu")
        driver.choose("day_pattern_add")
        driver.submit(name="", same_every_day=True)
        self.assertEqual(driver.result["errors"].get("name"), "name_required")
        driver.submit(name="Weekend", same_every_day=False, days=[])
        self.assertEqual(driver.result["errors"].get("days"), "days_required")

    def test_periods_with_several_timetables_asks_which(self) -> None:
        driver = OptionsDriver()
        driver.start()
        driver.choose("day_patterns_menu")
        driver.choose("day_pattern_duplicate")
        driver.submit(source="Every day", name="Weekend")
        driver.submit(
            name="Weekend", same_every_day=False, days=["sat", "sun", "holiday"]
        )
        driver.result = run(driver.flow.async_step_init())
        result = driver.choose("periods_pick_day_pattern")
        self.assertEqual(result["step_id"], "periods_pick_day_pattern")
        driver.submit(name="Weekend")
        self.assertEqual(driver.step, "periods_menu")

    def test_adding_and_removing_a_period(self) -> None:
        driver = OptionsDriver()
        driver.start()
        driver.choose("periods_pick_day_pattern")
        driver.choose("period_remove")
        driver.submit(period="16:00 to 24:00  Every day Peak")
        self.assertEqual(driver.step, "periods_menu")
        driver.choose("period_add")
        driver.submit(start="16:00:00", end="00:00:00", rate="Every day Peak")
        periods = driver.flow.working[CONST.CONF_DAY_PATTERNS][0][CONST.CONF_PERIODS]
        self.assertEqual(len(periods), 2)

    def test_a_period_ending_before_it_starts_is_refused(self) -> None:
        driver = OptionsDriver()
        driver.start()
        driver.choose("periods_pick_day_pattern")
        driver.choose("period_add")
        driver.submit(start="12:00:00", end="06:00:00", rate="Every day Peak")
        self.assertEqual(driver.result["errors"].get("end"), "end_before_start")

    def test_feed_in_rates_can_be_added_edited_and_removed(self) -> None:
        driver = OptionsDriver()
        driver.start()
        driver.choose("export_menu")
        driver.choose("export_rate_add")
        driver.submit(name="Evening", export_cents=12.0)
        self.assertEqual(driver.step, "export_menu")
        driver.choose("export_rate_pick")
        driver.submit(name="Evening")
        driver.submit(name="Evening peak", export_cents=14.0)
        self.assertEqual(
            driver.flow._export_rates()[0][CONST.CONF_NAME],
            "Evening peak",
        )
        driver.choose("export_rate_remove")
        driver.submit(name="Evening peak")
        self.assertEqual(driver.flow._export_rates(), [])

    def test_a_duplicate_feed_in_rate_is_refused(self) -> None:
        driver = OptionsDriver()
        driver.start()
        driver.choose("export_menu")
        driver.choose("export_rate_add")
        driver.submit(name="Evening", export_cents=12.0)
        driver.choose("export_rate_add")
        driver.submit(name="Evening", export_cents=9.0)
        self.assertEqual(driver.result["errors"].get("name"), "rate_exists")

    def test_feed_in_periods_reuse_the_period_screens(self) -> None:
        driver = OptionsDriver()
        driver.start()
        driver.choose("export_menu")
        driver.choose("export_rate_add")
        driver.submit(name="All day", export_cents=2.7)
        driver.choose("export_periods_pick")
        self.assertTrue(driver.flow._editing_export)
        self.assertEqual(driver.step, "periods_menu")
        driver.choose("period_add")
        driver.submit(start="00:00:00", end="00:00:00", rate="All day")
        pattern = driver.flow.working[CONST.CONF_DAY_PATTERNS][0]
        self.assertEqual(len(pattern[CONST.CONF_EXPORT_PERIODS]), 1)

    def test_general_settings_are_stored(self) -> None:
        driver = OptionsDriver()
        driver.start()
        driver.choose("general")
        driver.submit(
            daily_supply_charge_cents=99.0,
            monthly_charge=19.0,
        )
        self.assertEqual(driver.step, "init")
        self.assertEqual(driver.flow.working[CONST.CONF_MONTHLY_CHARGE], 19.0)

    def test_backwards_validity_is_refused(self) -> None:
        driver = OptionsDriver()
        driver.start()
        driver.choose("general")
        driver.submit(valid_from="2026-07-01", valid_to="2026-01-01")
        self.assertEqual(driver.result["errors"].get("valid_to"), "validity_backwards")

    def test_usage_tracking_links_a_select(self) -> None:
        driver = OptionsDriver()
        driver.start()
        driver.choose("usage_tracking")
        driver.choose("meter_link")
        driver.submit(tariff_selects=["select.meter"])
        self.assertEqual(
            driver.flow.working[CONST.CONF_TARIFF_SELECTS], ["select.meter"]
        )

    def test_creating_a_meter_needs_rates(self) -> None:
        driver = self._empty()
        driver.start()
        driver.choose("usage_tracking")
        self.assertEqual(driver.choose("meter_create")["step_id"], "rate_add")


class TestRuleLists(unittest.TestCase):
    """Two multi-selects, both seeded, both accepting a typed value.

    Each rule is typed once into whichever list it belongs to. What is stored
    is the union plus the enforceable subset, so anything reading the flat
    ``constraints`` list sees exactly what it always saw.
    """

    def _field(self, driver: OptionsDriver, key: str) -> Any:
        return _ha_stubs.field_for(driver.result, key)

    def _at_rate_form(self) -> OptionsDriver:
        driver = OptionsDriver()
        driver.start()
        driver.choose("rates_menu")
        driver.choose("rate_add")
        return driver

    def _last_rate(self, driver: OptionsDriver) -> dict[str, Any]:
        rates: list[dict[str, Any]] = driver.flow._rates()
        return rates[-1]

    def test_both_lists_are_on_the_form_and_seeded(self) -> None:
        driver = self._at_rate_form()
        for key in (
            CONST.CONF_INFORMATION_CONSTRAINTS,
            CONST.CONF_ENFORCEABLE_CONSTRAINTS,
        ):
            _, field = self._field(driver, key)
            self.assertEqual(
                sorted(field.config.options), sorted(CONST.KNOWN_CONSTRAINTS)
            )
            self.assertTrue(field.config.multiple)
            self.assertTrue(field.config.custom_value)

    def test_an_information_rule_is_stored_but_not_enforceable(self) -> None:
        driver = self._at_rate_form()
        driver.submit(
            name="Night",
            import_cents=39.6,
            information_constraints=["precool_opportunity"],
        )
        rate = self._last_rate(driver)
        self.assertEqual(rate[CONST.CONF_CONSTRAINTS], ["precool_opportunity"])
        self.assertEqual(rate[CONST.CONF_ENFORCEABLE_CONSTRAINTS], [])

    def test_an_enforceable_rule_lands_in_both_the_union_and_the_subset(self) -> None:
        driver = self._at_rate_form()
        driver.submit(
            name="Night", import_cents=39.6, enforceable_constraints=["no_grid_import"]
        )
        rate = self._last_rate(driver)
        self.assertEqual(rate[CONST.CONF_CONSTRAINTS], ["no_grid_import"])
        self.assertEqual(rate[CONST.CONF_ENFORCEABLE_CONSTRAINTS], ["no_grid_import"])

    def test_a_mixture_keeps_the_roles_apart(self) -> None:
        driver = self._at_rate_form()
        driver.submit(
            name="Peak",
            import_cents=56.88,
            information_constraints=["precool_opportunity"],
            enforceable_constraints=["no_grid_import"],
        )
        rate = self._last_rate(driver)
        # Stored sorted. A rate's rules are a set; the order they were typed in
        # is not a fact about the plan, and a stable order is what keeps an
        # unrelated edit from showing up as a change to the rules.
        self.assertEqual(
            rate[CONST.CONF_CONSTRAINTS], ["no_grid_import", "precool_opportunity"]
        )
        self.assertEqual(rate[CONST.CONF_ENFORCEABLE_CONSTRAINTS], ["no_grid_import"])

    def test_a_rule_in_both_lists_is_refused(self) -> None:
        driver = self._at_rate_form()
        driver.submit(
            name="Peak",
            import_cents=56.88,
            information_constraints=["no_grid_import"],
            enforceable_constraints=["no_grid_import"],
        )
        self.assertEqual(
            driver.result["errors"].get(CONST.CONF_ENFORCEABLE_CONSTRAINTS),
            "rule_in_both_lists",
        )

    def test_a_typed_rule_joins_the_list_for_the_next_rate(self) -> None:
        driver = self._at_rate_form()
        driver.submit(
            name="Night", import_cents=39.6, enforceable_constraints=["hold_battery"]
        )
        driver.choose("rate_add")
        for key in (
            CONST.CONF_INFORMATION_CONSTRAINTS,
            CONST.CONF_ENFORCEABLE_CONSTRAINTS,
        ):
            _, field = self._field(driver, key)
            self.assertIn("hold_battery", field.config.options)

    def test_duplicates_within_one_list_collapse(self) -> None:
        driver = self._at_rate_form()
        driver.submit(
            name="Night",
            import_cents=39.6,
            information_constraints=["no_grid_import", "no_grid_import"],
        )
        self.assertEqual(
            self._last_rate(driver)[CONST.CONF_CONSTRAINTS], ["no_grid_import"]
        )

    def test_editing_a_rate_puts_each_rule_back_in_its_own_list(self) -> None:
        driver = self._at_rate_form()
        driver.submit(
            name="Night",
            import_cents=39.6,
            information_constraints=["precool_opportunity"],
            enforceable_constraints=["no_grid_import"],
        )
        driver.choose("rate_pick")
        driver.submit(name="test_plan.every_day.import.night")
        info_key, _ = self._field(driver, CONST.CONF_INFORMATION_CONSTRAINTS)
        enf_key, _ = self._field(driver, CONST.CONF_ENFORCEABLE_CONSTRAINTS)
        self.assertEqual(info_key.default(), ["precool_opportunity"])
        self.assertEqual(enf_key.default(), ["no_grid_import"])

    def test_a_plan_written_before_the_distinction_loads_as_information(self) -> None:
        """Existing rules keep the meaning they had rather than being promoted."""
        data = sample_options()
        rate_in(data, 0).pop(CONST.CONF_ENFORCEABLE_CONSTRAINTS, None)
        driver = OptionsDriver(data)
        driver.start()
        driver.choose("rates_menu")
        driver.choose("rate_pick")
        driver.submit(name="test_plan.every_day.import.every_day_off_peak")
        info_key, _ = self._field(driver, CONST.CONF_INFORMATION_CONSTRAINTS)
        enf_key, _ = self._field(driver, CONST.CONF_ENFORCEABLE_CONSTRAINTS)
        self.assertEqual(info_key.default(), ["grid_charge_battery"])
        self.assertEqual(enf_key.default(), [])


class TestTheSetupFormCanSetRules(unittest.TestCase):
    """The bug: the setup form never asked, and wrote an empty list anyway."""

    def test_the_setup_rate_form_opens_on_a_name_and_a_price(self) -> None:
        """P29: what every rate has is loose; the rest is in a section."""
        schema = PKG.config_flow._rate_schema(
            {}, [], fields=PKG.config_flow.SETUP_RATE_FIELDS
        )
        top = [getattr(key, "schema", key) for key in schema.schema]
        self.assertEqual(
            top,
            [
                CONST.CONF_NAME,
                CONST.CONF_IMPORT_CENTS,
                CONST.SECTION_DEMAND,
                CONST.SECTION_ALLOWANCE,
                CONST.SECTION_CONSTRAINTS,
            ],
        )

    def test_every_section_starts_collapsed(self) -> None:
        schema = PKG.config_flow._rate_schema({}, ["Other"])
        sections = [
            value
            for value in schema.schema.values()
            if isinstance(value, _ha_stubs.Section)
        ]
        self.assertEqual(len(sections), 3)
        for group in sections:
            self.assertTrue(group.options["collapsed"])

    def test_each_section_holds_its_own_fields(self) -> None:
        schema = PKG.config_flow._rate_schema({}, ["Other"])
        grouped = {
            getattr(key, "schema", key): _ha_stubs.field_names(value.schema)
            for key, value in schema.schema.items()
            if isinstance(value, _ha_stubs.Section)
        }
        self.assertEqual(
            grouped[CONST.SECTION_DEMAND],
            {
                CONST.CONF_DEMAND_PERIOD,
                CONST.CONF_DEMAND_RATE,
                CONST.CONF_DEMAND_INTERVAL,
                CONST.CONF_DEMAND_BASIS,
            },
        )
        self.assertEqual(
            grouped[CONST.SECTION_ALLOWANCE],
            {
                CONST.CONF_HAS_ALLOWANCE,
                CONST.CONF_RATE_ALLOWANCE_KWH,
                CONST.CONF_FALLBACK_RATE,
                CONST.CONF_ALLOWANCE_PERIOD,
            },
        )
        self.assertEqual(
            grouped[CONST.SECTION_CONSTRAINTS],
            {
                CONST.CONF_INFORMATION_CONSTRAINTS,
                CONST.CONF_ENFORCEABLE_CONSTRAINTS,
            },
        )

    def test_coasting_is_a_rule_and_not_a_field(self) -> None:
        """P29: it says what the other rules say, so it is declared like them."""
        self.assertNotIn(
            "coasting_permitted",
            _ha_stubs.field_names(PKG.config_flow._rate_schema({}, ["Other"])),
        )
        self.assertIn(CONST.CONSTRAINT_COASTING_PERMITTED, CONST.KNOWN_CONSTRAINTS)

    def test_setup_offers_the_allowance_and_its_accounting_period(self) -> None:
        """Asking the minimum is about what is required, not what is offered.

        An allowance declared during setup should not have to be declared a
        second time in Configure. There is no counting tickbox any more
        (rule 7, revoked) — what is offered instead is which accounting
        period the cap belongs to. The import meter itself is no longer
        asked here at all (Gap #7): it is mandatory for the whole plan,
        asked once on the charges screen, not per rate.
        """
        fields = _ha_stubs.field_names(
            PKG.config_flow._rate_schema(
                {}, ["Other"], fields=PKG.config_flow.SETUP_RATE_FIELDS
            )
        )
        self.assertIn(CONST.CONF_RATE_ALLOWANCE_KWH, fields)
        self.assertIn(CONST.CONF_FALLBACK_RATE, fields)
        self.assertIn(CONST.CONF_ALLOWANCE_PERIOD, fields)
        self.assertNotIn(CONST.CONF_IMPORT_ENERGY_SENSOR, fields)
        self.assertNotIn("count_allowance", fields)

    def test_the_edit_form_is_the_same_form_unfiltered(self) -> None:
        """One definition. The setup form asking for less is the only difference.

        fallback_rate used to be the one field this test named as the
        difference between an empty and a populated fallback_options list —
        that was the P36 bug: the field was gated on sibling existence
        rather than on whether the rate declares an allowance. It is now
        present regardless, so setup and full carry the same field names for
        any given fallback_options.
        """
        setup = _ha_stubs.field_names(
            PKG.config_flow._rate_schema(
                {}, [], fields=PKG.config_flow.SETUP_RATE_FIELDS
            )
        )
        full = _ha_stubs.field_names(PKG.config_flow._rate_schema({}, []))
        self.assertEqual(setup, full)

    def test_no_export_field_is_on_an_import_rate_form(self) -> None:
        """P32: import and export are separate flows on the forms as well."""
        full = _ha_stubs.field_names(PKG.config_flow._rate_schema({}, ["Other"]))
        self.assertNotIn(CONST.CONF_EXPORT_ALLOWANCE_KWH, full)
        self.assertNotIn(CONST.CONF_EXPORT_FALLBACK_CENTS, full)

    def test_rules_entered_at_setup_reach_the_stored_rate(self) -> None:
        record = PKG.config_flow._rate_record(
            {
                CONST.CONF_NAME: "Peak",
                CONST.CONF_IMPORT_CENTS: 56.88,
                CONST.CONF_INFORMATION_CONSTRAINTS: ["precool_opportunity"],
                CONST.CONF_ENFORCEABLE_CONSTRAINTS: ["no_grid_import"],
            }
        )
        self.assertEqual(
            record[CONST.CONF_CONSTRAINTS], ["no_grid_import", "precool_opportunity"]
        )
        self.assertEqual(record[CONST.CONF_ENFORCEABLE_CONSTRAINTS], ["no_grid_import"])


class TestCountingSitsWithTheCap(unittest.TestCase):
    """The meter is asked once, for the whole plan, not per rate.

    It used to be a Configure screen of its own, which meant an allowance was
    declared in one place and counted in another (P24). Rule 7 was then
    revoked: there is no tickbox any more, because there is no opt-in — a
    declared cap is counted whenever a meter is nominated. Rule 6 was later
    also revoked (Gap #7): the meter used to be asked per rate, required
    only once that one rate declared a demand charge or an allowance — a
    demand-only rate never opened the Allowance section that field lived in,
    and was rejected for a field it was never shown. It is asked once now,
    on the charges screen (setup) and the general screen (Configure),
    mandatory for every plan regardless of what any individual rate
    declares.
    """

    def test_the_separate_screen_is_gone(self) -> None:
        self.assertFalse(
            hasattr(
                PKG.config_flow.AbodePowerTariffsOptionsFlow,
                "async_step_allowance_counting",
            )
        )

    def test_the_tickbox_is_gone(self) -> None:
        """Rule 7, inverted. There is no opt-in field left to find."""
        fields = _ha_stubs.field_names(PKG.config_flow._rate_schema({}, ["Other"]))
        self.assertNotIn("count_allowance", fields)

    def test_the_rate_form_carries_the_allowance_period_but_not_the_meter(
        self,
    ) -> None:
        fields = _ha_stubs.field_names(PKG.config_flow._rate_schema({}, ["Other"]))
        self.assertIn(CONST.CONF_RATE_ALLOWANCE_KWH, fields)
        self.assertIn(CONST.CONF_ALLOWANCE_PERIOD, fields)
        self.assertNotIn(CONST.CONF_IMPORT_ENERGY_SENSOR, fields)

    def test_the_meter_is_required_on_the_charges_screen(self) -> None:
        flow = PKG.config_flow.AbodePowerTariffsConfigFlow()
        run(flow.async_step_user())
        run(
            flow.async_step_user(
                {
                    CONST.CONF_PLAN_NAME: "P",
                    CONST.CONF_PLAN_DESCRIPTION: "",
                    CONST.CONF_SINGLE_RATE: False,
                    CONST.CONF_HAS_EXPORT: False,
                }
            )
        )
        result = run(
            flow.async_step_charges(
                {
                    CONST.CONF_SUPPLY_CHARGE_CENTS: 0.0,
                    CONST.CONF_MONTHLY_CHARGE: 0.0,
                    CONST.CONF_BILLING_CYCLE_DAY: 0,
                    CONST.CONF_PRICES_INCLUDE_GST: True,
                    CONST.CONF_GST_PERCENT: 10.0,
                    CONST.CONF_IMPORT_ENERGY_SENSOR: "",
                }
            )
        )
        self.assertEqual(
            result["errors"].get(CONST.CONF_IMPORT_ENERGY_SENSOR),
            "energy_sensor_required",
        )

    def test_the_meter_is_required_on_the_general_screen(self) -> None:
        driver = OptionsDriver()
        driver.start()
        driver.choose("general")
        result = driver.submit(**{CONST.CONF_IMPORT_ENERGY_SENSOR: ""})
        self.assertEqual(
            result["errors"].get(CONST.CONF_IMPORT_ENERGY_SENSOR),
            "energy_sensor_required",
        )

    def test_the_meter_is_not_stored_on_the_rate(self) -> None:
        """Plan-level. One meter, one answer."""
        record = PKG.config_flow._rate_record(
            {
                CONST.CONF_NAME: "Off Peak",
                CONST.CONF_IMPORT_CENTS: 22.0,
                CONST.CONF_IMPORT_ENERGY_SENSOR: "sensor.grid_import",
            }
        )
        self.assertNotIn(CONST.CONF_IMPORT_ENERGY_SENSOR, record)
        self.assertNotIn("count_allowance", record)


class TestTheDemandRateSitsOnTheRate(unittest.TestCase):
    """P27: the demand rate is declared on the rate it belongs to.

    Not on the plan-wide charges screen, and not silently required until the
    demand period box is actually ticked.
    """

    def test_the_charges_screen_no_longer_asks_for_it(self) -> None:
        flow = PKG.config_flow.AbodePowerTariffsConfigFlow()
        result = run(flow.async_step_charges())
        fields = _ha_stubs.field_names(result["data_schema"])
        self.assertNotIn(CONST.CONF_DEMAND_RATE, fields)

    def test_a_demand_period_with_no_rate_is_refused(self) -> None:
        self.assertTrue(
            PKG.config_flow._demand_without_rate(
                {CONST.CONF_DEMAND_PERIOD: True, CONST.CONF_DEMAND_RATE: 0.0}
            )
        )
        self.assertTrue(
            PKG.config_flow._demand_without_rate({CONST.CONF_DEMAND_PERIOD: True})
        )

    def test_unticked_or_answered_is_not_refused(self) -> None:
        self.assertFalse(
            PKG.config_flow._demand_without_rate({CONST.CONF_DEMAND_PERIOD: False})
        )
        self.assertFalse(
            PKG.config_flow._demand_without_rate(
                {CONST.CONF_DEMAND_PERIOD: True, CONST.CONF_DEMAND_RATE: 18.4}
            )
        )

    def test_a_demand_period_with_no_rate_is_refused_on_the_rates_step(self) -> None:
        """A meter is supplied so this exercises the demand guard specifically,
        not the meter guard that now also fires on a bare demand_period."""
        flow = PKG.config_flow.AbodePowerTariffsConfigFlow()
        flow._name = "P"
        result = run(
            flow.async_step_rates(
                {
                    CONST.CONF_NAME: "Peak",
                    CONST.CONF_IMPORT_CENTS: 50.0,
                    CONST.CONF_DEMAND_PERIOD: True,
                    CONST.CONF_DEMAND_RATE: 0.0,
                    CONST.CONF_IMPORT_ENERGY_SENSOR: "sensor.grid_import",
                    CONST.CONF_ON_SUBMIT: "submit_add",
                }
            )
        )
        self.assertEqual(
            result["errors"], {CONST.CONF_DEMAND_RATE: "demand_rate_required"}
        )

    def test_a_bare_demand_period_with_no_rate_is_refused(self) -> None:
        """The meter is no longer checked here at all (Gap #7) — it is asked
        once, earlier, on the charges screen. What is still checked here is
        the demand rate itself: declaring the period without a number to
        publish is refused the same way it always was.
        """
        flow = PKG.config_flow.AbodePowerTariffsConfigFlow()
        flow._name = "P"
        result = run(
            flow.async_step_rates(
                {
                    CONST.CONF_NAME: "Peak",
                    CONST.CONF_IMPORT_CENTS: 50.0,
                    CONST.CONF_DEMAND_PERIOD: True,
                    CONST.CONF_DEMAND_RATE: 0.0,
                    CONST.CONF_ON_SUBMIT: "submit_add",
                }
            )
        )
        self.assertEqual(
            result["errors"],
            {CONST.CONF_DEMAND_RATE: "demand_rate_required"},
        )

    def test_a_demand_rate_declared_at_setup_reaches_the_stored_rate(self) -> None:
        flow = PKG.config_flow.AbodePowerTariffsConfigFlow()
        flow._name = "P"
        run(
            flow.async_step_rates(
                {
                    CONST.CONF_NAME: "Peak",
                    CONST.CONF_IMPORT_CENTS: 50.0,
                    CONST.CONF_DEMAND_PERIOD: True,
                    CONST.CONF_DEMAND_RATE: 18.4,
                    CONST.CONF_IMPORT_ENERGY_SENSOR: "sensor.grid_import",
                    CONST.CONF_ON_SUBMIT: "submit_add",
                }
            )
        )
        stored = flow._rates[0]
        self.assertTrue(stored[CONST.CONF_DEMAND_PERIOD])
        self.assertAlmostEqual(stored[CONST.CONF_DEMAND_RATE], 18.4)

    def test_two_rates_can_carry_two_different_demand_rates(self) -> None:
        """The point of moving it off the plan: it no longer has to be shared."""
        rate_a = PKG.config_flow._rate_record(
            {
                CONST.CONF_NAME: "Summer Peak",
                CONST.CONF_IMPORT_CENTS: 50.0,
                CONST.CONF_DEMAND_PERIOD: True,
                CONST.CONF_DEMAND_RATE: 18.4,
            }
        )
        rate_b = PKG.config_flow._rate_record(
            {
                CONST.CONF_NAME: "Winter Peak",
                CONST.CONF_IMPORT_CENTS: 55.0,
                CONST.CONF_DEMAND_PERIOD: True,
                CONST.CONF_DEMAND_RATE: 9.2,
            }
        )
        self.assertNotEqual(
            rate_a[CONST.CONF_DEMAND_RATE], rate_b[CONST.CONF_DEMAND_RATE]
        )

    def test_demand_period_and_rate_are_on_the_setup_form(self) -> None:
        """Rule 6, and P27 item 4: appears at setup, not just Configure."""
        fields = _ha_stubs.field_names(
            PKG.config_flow._rate_schema(
                {}, [], fields=PKG.config_flow.SETUP_RATE_FIELDS
            )
        )
        self.assertIn(CONST.CONF_DEMAND_PERIOD, fields)
        self.assertIn(CONST.CONF_DEMAND_RATE, fields)


class TestTheBillingCycleDay(unittest.TestCase):
    """A declared fact. The day is published; nothing is computed from it."""

    def test_the_day_round_trips_through_storage(self) -> None:
        plan = PKG.plan.Plan.from_dict({"name": "P", CONST.CONF_BILLING_CYCLE_DAY: 12})
        self.assertEqual(plan.billing_cycle_day, 12)
        self.assertEqual(plan.as_dict()[CONST.CONF_BILLING_CYCLE_DAY], 12)

    def test_no_day_entered_is_no_day(self) -> None:
        self.assertIsNone(PKG.plan.Plan.from_dict({"name": "P"}).billing_cycle_day)
        self.assertIsNone(
            PKG.plan.Plan.from_dict(
                {"name": "P", CONST.CONF_BILLING_CYCLE_DAY: 0}
            ).billing_cycle_day
        )

    def test_a_day_no_month_has_is_refused(self) -> None:
        """A retailer bills on the same day every month, so 29 to 31 cannot be it."""
        for day in (29, 30, 31):
            plan = PKG.plan.Plan.from_dict(
                {"name": "P", CONST.CONF_BILLING_CYCLE_DAY: day}
            )
            problems = [str(problem) for problem in PKG.validate.validate_plan(plan)]
            self.assertTrue(
                any("does not exist in every month" in problem for problem in problems),
                problems,
            )

    def test_one_to_twenty_eight_is_accepted(self) -> None:
        for day in (1, 15, 28):
            plan = PKG.plan.Plan.from_dict(
                {"name": "P", CONST.CONF_BILLING_CYCLE_DAY: day}
            )
            problems = [str(problem) for problem in PKG.validate.validate_plan(plan)]
            self.assertFalse(
                any("every month" in problem for problem in problems), problems
            )


def scoped_options() -> dict[str, Any]:
    """Two timetables, each with its own rates, nested inside it (Gap #1)."""
    return {
        CONST.CONF_DAY_PATTERNS: [
            {
                CONST.CONF_NAME: "Weekday",
                CONST.CONF_DAYS: ["mon", "tue", "wed", "thu", "fri", "holiday"],
                CONST.CONF_RATES: [
                    {
                        CONST.CONF_NAME: "Off Peak",
                        CONST.CONF_IMPORT_CENTS: 19.8,
                    },
                    {
                        CONST.CONF_NAME: "Peak",
                        CONST.CONF_IMPORT_CENTS: 56.88,
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
                CONST.CONF_EXPORT_SAME_ALL_DAY: True,
                CONST.CONF_EXPORT_FLAT_CENTS: 2.7,
            },
            {
                CONST.CONF_NAME: "Weekend",
                CONST.CONF_DAYS: ["sat", "sun"],
                CONST.CONF_RATES: [
                    {
                        CONST.CONF_NAME: "Peak",
                        CONST.CONF_IMPORT_CENTS: 30.0,
                    },
                ],
                CONST.CONF_PERIODS: [
                    {
                        CONST.CONF_START: "00:00",
                        CONST.CONF_END: "24:00",
                        CONST.CONF_RATE: "Peak",
                    }
                ],
                CONST.CONF_EXPORT_SAME_ALL_DAY: True,
                CONST.CONF_EXPORT_FLAT_CENTS: 2.7,
            },
        ],
        CONST.CONF_SUPPLY_CHARGE_CENTS: 116.6,
    }


class TestATimetableRenameTakesItsRates(unittest.TestCase):
    """P31 change one. Renaming is only a rename; the rates go with it."""

    def _rename(self, previous: str, current: str) -> Any:
        driver = OptionsDriver(scoped_options())
        driver.start()
        driver.choose("day_patterns_menu")
        driver.choose("day_pattern_pick")
        driver.submit(name=previous)
        driver.submit(name=current)
        return driver

    def test_the_rates_follow_the_new_name(self) -> None:
        driver = self._rename("Weekday", "Week day")
        scoped = {
            rate[CONST.CONF_NAME]: rate.get(CONST.CONF_TIMETABLE)
            for rate in driver.flow._rates()
            if rate.get(CONST.CONF_TIMETABLE) != "Weekend"
        }
        self.assertEqual(scoped, {"Off Peak": "Week day", "Peak": "Week day"})

    def test_the_renamed_plan_still_validates(self) -> None:
        driver = self._rename("Weekday", "Week day")
        plan = Plan.from_dict({**driver.flow.working, CONST.CONF_NAME: "Test Plan"})
        self.assertEqual(PKG.validate.validate_plan(plan), [])

    def test_the_renamed_plan_still_resolves(self) -> None:
        driver = self._rename("Weekday", "Week day")
        plan = Plan.from_dict({**driver.flow.working, CONST.CONF_NAME: "Test Plan"})
        resolution = plan.resolve(date(2026, 8, 20), 18 * 60, False)
        self.assertIsNotNone(resolution)
        assert resolution is not None
        self.assertEqual(resolution.qualified_name, "test_plan.week_day.import.peak")

    def test_the_other_timetables_rates_are_left_alone(self) -> None:
        driver = self._rename("Weekday", "Week day")
        weekend = [
            rate
            for rate in driver.flow._rates()
            if rate.get(CONST.CONF_TIMETABLE) == "Weekend"
        ]
        self.assertEqual(len(weekend), 1)


class TestThePeriodScreenIsScopedToItsTimetable(unittest.TestCase):
    """P31 change two. weekday.peak is not visible under the weekend."""

    def _period_form(self, timetable: str, options: Any = None) -> Any:
        driver = OptionsDriver(options or scoped_options())
        driver.start()
        driver.choose("periods_pick_day_pattern")
        driver.submit(name=timetable)
        driver.choose("period_add")
        return driver

    def _offered(self, driver: Any) -> list[str]:
        return _ha_stubs.options_for(driver.result, CONST.CONF_RATE)

    def test_the_weekend_is_offered_only_its_own_rate(self) -> None:
        driver = self._period_form("Weekend")
        self.assertEqual(self._offered(driver), ["test_plan.weekend.import.peak"])

    def test_the_weekday_is_offered_only_its_own_rates(self) -> None:
        driver = self._period_form("Weekday")
        self.assertEqual(
            sorted(self._offered(driver)),
            [
                "test_plan.weekday.import.off_peak",
                "test_plan.weekday.import.peak",
            ],
        )

    def test_a_chosen_identifier_is_stored_as_the_rate_name(self) -> None:
        driver = self._period_form("Weekend")
        driver.submit(
            start="00:00:00", end="12:00:00", rate="test_plan.weekend.import.peak"
        )
        weekend = driver.flow.working[CONST.CONF_DAY_PATTERNS][1]
        self.assertEqual(
            [period[CONST.CONF_RATE] for period in weekend[CONST.CONF_PERIODS]],
            ["Peak", "Peak"],
        )

    def test_a_timetable_with_no_rates_opens_the_rate_form(self) -> None:
        options = scoped_options()
        options[CONST.CONF_DAY_PATTERNS].append(
            {
                CONST.CONF_NAME: "Summer",
                CONST.CONF_DAYS: ["sat", "sun"],
                CONST.CONF_PERIODS: [],
                CONST.CONF_EXPORT_SAME_ALL_DAY: True,
                CONST.CONF_EXPORT_FLAT_CENTS: 0.0,
            }
        )
        driver = self._period_form("Summer", options)
        self.assertEqual(driver.step, "rate_add")


class TestTheRateFormIsSectioned(unittest.TestCase):
    """P29: two unrelated declarations no longer run together in one list."""

    def _at_rate_form(self) -> OptionsDriver:
        driver = OptionsDriver()
        driver.start()
        driver.choose("rates_menu")
        driver.choose("rate_add")
        return driver

    def test_a_sectioned_form_still_round_trips_its_defaults(self) -> None:
        driver = self._at_rate_form()
        driver.submit(name="Shoulder", import_cents=32.1)
        self.assertEqual(driver.step, "rates_menu")
        stored = driver.flow._rates()[-1]
        self.assertEqual(stored[CONST.CONF_NAME], "Shoulder")

    def test_the_payload_arrives_nested_and_is_read_anyway(self) -> None:
        """The handler is given sections; a field means the same wherever shown."""
        record = PKG.config_flow._rate_record(
            PKG.config_flow.flatten_sections(
                {
                    CONST.CONF_NAME: "Peak",
                    CONST.CONF_IMPORT_CENTS: 56.88,
                    CONST.SECTION_DEMAND: {
                        CONST.CONF_DEMAND_PERIOD: True,
                        CONST.CONF_DEMAND_RATE: 12.5,
                    },
                    CONST.SECTION_CONSTRAINTS: {
                        CONST.CONF_INFORMATION_CONSTRAINTS: ["precool_opportunity"],
                        CONST.CONF_ENFORCEABLE_CONSTRAINTS: ["no_grid_import"],
                    },
                }
            )
        )
        self.assertTrue(record[CONST.CONF_DEMAND_PERIOD])
        self.assertEqual(record[CONST.CONF_DEMAND_RATE], 12.5)
        self.assertEqual(
            sorted(record[CONST.CONF_CONSTRAINTS]),
            ["no_grid_import", "precool_opportunity"],
        )

    def test_the_accumulation_fields_no_longer_say_not_implemented(self) -> None:
        """P35, inverted. Counting shipped; the caveat that it hadn't is stale."""
        strings = json.loads(
            (Path(PKG.config_flow.__file__).parent / "strings.json").read_text()
        )
        for root, step in (("config", "rates"), ("options", "rate_add")):
            labels = strings[root]["step"][step]["sections"][CONST.SECTION_ALLOWANCE][
                "data"
            ]
            for field in (
                CONST.CONF_RATE_ALLOWANCE_KWH,
                CONST.CONF_FALLBACK_RATE,
                CONST.CONF_ALLOWANCE_PERIOD,
            ):
                self.assertNotIn("not yet implemented", labels[field], (root, field))
            self.assertNotIn("count_allowance", labels, root)

    def test_coasting_declared_as_a_rule_reaches_the_published_rate(self) -> None:
        driver = self._at_rate_form()
        driver.submit(
            name="Drift",
            import_cents=10.0,
            **{
                CONST.SECTION_CONSTRAINTS: {
                    CONST.CONF_INFORMATION_CONSTRAINTS: [
                        CONST.CONSTRAINT_COASTING_PERMITTED
                    ],
                    CONST.CONF_ENFORCEABLE_CONSTRAINTS: [],
                }
            },
        )
        plan = Plan.from_dict({**driver.flow.working, CONST.CONF_NAME: "Test Plan"})
        rate = plan.rate_by_name("Drift", "Every day")
        assert rate is not None
        self.assertTrue(rate.coasting_permitted)

    def test_a_rate_without_the_rule_does_not_permit_coasting(self) -> None:
        plan = Plan.from_dict({**sample_options(), CONST.CONF_NAME: "Test Plan"})
        rate = plan.rate_by_name("Every day Peak", "Every day")
        assert rate is not None
        self.assertFalse(rate.coasting_permitted)
