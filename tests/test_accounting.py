"""The reset arithmetic, written before anything accumulates.

This is the first place in the component where a wrong instant costs money
rather than display, so the daylight-saving cases are asserted here and the
accumulation built on top of them afterwards.

Australia/Sydney is used throughout because it is the owner's zone and both
transitions land at 02:00 local: the clocks go forward on the first Sunday in
October and back on the first Sunday in April.
"""

from __future__ import annotations

import unittest
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from _pure import load

pure = load()
accounting = pure.accounting
plan_module = pure.plan

SYDNEY = ZoneInfo("Australia/Sydney")
SPRING_FORWARD = date(2026, 10, 4)
FALL_BACK = date(2026, 4, 5)


class TestCycleBoundaries(unittest.TestCase):
    """Where a billing cycle starts and ends, on a day that is not the 1st."""

    def test_a_date_on_or_after_the_billing_day_starts_this_month(self) -> None:
        self.assertEqual(
            accounting.cycle_start(date(2026, 5, 20), 12), date(2026, 5, 12)
        )

    def test_a_date_before_the_billing_day_belongs_to_last_months_cycle(self) -> None:
        self.assertEqual(
            accounting.cycle_start(date(2026, 5, 3), 12), date(2026, 4, 12)
        )

    def test_january_reaches_back_into_the_previous_year(self) -> None:
        self.assertEqual(
            accounting.cycle_start(date(2026, 1, 5), 12), date(2025, 12, 12)
        )

    def test_the_cycle_ends_the_day_before_the_next_one_starts(self) -> None:
        self.assertEqual(accounting.cycle_end(date(2026, 5, 20), 12), date(2026, 6, 11))

    def test_an_undeclared_billing_day_bills_from_the_first(self) -> None:
        self.assertEqual(
            accounting.cycle_start(date(2026, 5, 20), None), date(2026, 5, 1)
        )

    def test_a_stored_day_past_28_is_clamped_rather_than_crashing(self) -> None:
        # Declaration refuses these; a plan written by hand could still hold
        # one. Clamped to the 28th, so 27 February still belongs to the cycle
        # that opened on 28 January rather than raising on a date that does
        # not exist.
        self.assertEqual(
            accounting.cycle_start(date(2026, 2, 27), 31), date(2026, 1, 28)
        )
        self.assertEqual(
            accounting.cycle_start(date(2026, 3, 1), 31), date(2026, 2, 28)
        )


class TestDaysAreCalendarDays(unittest.TestCase):
    """Rule 4. A day is 23, 24 or 25 hours and the count does not care."""

    def test_february_is_28_days(self) -> None:
        self.assertEqual(accounting.days_in_cycle(date(2026, 2, 10), 1), 28)

    def test_the_cycle_holding_the_short_day_has_its_ordinary_length(self) -> None:
        # October 2026 contains the 23-hour day. A cycle counted in 24-hour
        # spans would come to 30 days and 23 hours and round to the wrong
        # number, which a per-day demand charge would then bill.
        self.assertEqual(accounting.days_in_cycle(SPRING_FORWARD, 1), 31)

    def test_the_cycle_holding_the_long_day_has_its_ordinary_length(self) -> None:
        self.assertEqual(accounting.days_in_cycle(FALL_BACK, 1), 30)

    def test_a_cycle_starting_mid_month_spans_two_months(self) -> None:
        self.assertEqual(accounting.days_in_cycle(date(2026, 5, 20), 12), 31)

    def test_days_elapsed_counts_the_current_day(self) -> None:
        self.assertEqual(accounting.days_elapsed_in_cycle(date(2026, 5, 12), 12), 1)
        self.assertEqual(accounting.days_elapsed_in_cycle(date(2026, 5, 20), 12), 9)


class TestCycleIdentity(unittest.TestCase):
    """Two figures belong to the same cycle when their keys match."""

    def test_two_days_inside_one_cycle_share_a_key(self) -> None:
        self.assertEqual(
            accounting.cycle_key(date(2026, 5, 12), 12),
            accounting.cycle_key(date(2026, 6, 11), 12),
        )

    def test_the_billing_day_starts_a_different_cycle(self) -> None:
        self.assertNotEqual(
            accounting.cycle_key(date(2026, 6, 11), 12),
            accounting.cycle_key(date(2026, 6, 12), 12),
        )

    def test_a_cycle_containing_a_transition_is_still_one_cycle(self) -> None:
        self.assertEqual(
            accounting.cycle_key(date(2026, 10, 1), 1),
            accounting.cycle_key(date(2026, 10, 31), 1),
        )


class TestIntervalAlignment(unittest.TestCase):
    """Intervals run on the clock, not from whenever the meter last spoke."""

    def test_a_half_hour_interval_starts_on_the_hour(self) -> None:
        moment = datetime(2026, 5, 20, 14, 7, tzinfo=SYDNEY)
        start = accounting.interval_start(moment, 30, SYDNEY)
        self.assertEqual(start.astimezone(SYDNEY).hour, 14)
        self.assertEqual(start.astimezone(SYDNEY).minute, 0)

    def test_a_half_hour_interval_starts_on_the_half_hour(self) -> None:
        moment = datetime(2026, 5, 20, 14, 47, tzinfo=SYDNEY)
        start = accounting.interval_start(moment, 30, SYDNEY)
        self.assertEqual(start.astimezone(SYDNEY).minute, 30)

    def test_a_quarter_hour_interval_uses_the_quarter_grid(self) -> None:
        moment = datetime(2026, 5, 20, 14, 47, tzinfo=SYDNEY)
        start = accounting.interval_start(moment, 15, SYDNEY)
        self.assertEqual(start.astimezone(SYDNEY).minute, 45)

    def test_instantaneous_has_no_interval(self) -> None:
        moment = datetime(2026, 5, 20, 14, 47, tzinfo=SYDNEY)
        self.assertIsNone(accounting.interval_start(moment, 0, SYDNEY))
        self.assertIsNone(accounting.interval_key(moment, 0, SYDNEY))

    def test_two_moments_in_one_interval_share_a_key(self) -> None:
        first = datetime(2026, 5, 20, 14, 1, tzinfo=SYDNEY)
        second = datetime(2026, 5, 20, 14, 29, tzinfo=SYDNEY)
        self.assertEqual(
            accounting.interval_key(first, 30, SYDNEY),
            accounting.interval_key(second, 30, SYDNEY),
        )

    def test_the_next_interval_has_a_different_key(self) -> None:
        first = datetime(2026, 5, 20, 14, 29, tzinfo=SYDNEY)
        second = datetime(2026, 5, 20, 14, 31, tzinfo=SYDNEY)
        self.assertNotEqual(
            accounting.interval_key(first, 30, SYDNEY),
            accounting.interval_key(second, 30, SYDNEY),
        )


class TestIntervalsAcrossTheRepeatedHour(unittest.TestCase):
    """The morning the clocks go back, 02:30 comes round twice."""

    def _both_passes(self) -> tuple[datetime, datetime]:
        # 02:30 local on the fall-back morning names two real instants an hour
        # apart. Built in UTC so each is unambiguous.
        first = datetime(2026, 4, 4, 15, 30, tzinfo=UTC)  # 02:30 AEDT
        second = datetime(2026, 4, 4, 16, 30, tzinfo=UTC)  # 02:30 AEST
        self.assertEqual(first.astimezone(SYDNEY).hour, 2)
        self.assertEqual(second.astimezone(SYDNEY).hour, 2)
        self.assertEqual(first.astimezone(SYDNEY).minute, 30)
        self.assertEqual(second.astimezone(SYDNEY).minute, 30)
        return first, second

    def test_the_two_passes_are_two_different_intervals(self) -> None:
        first, second = self._both_passes()
        self.assertNotEqual(
            accounting.interval_key(first, 30, SYDNEY),
            accounting.interval_key(second, 30, SYDNEY),
        )

    def test_the_second_pass_gets_the_start_that_actually_happened(self) -> None:
        _, second = self._both_passes()
        start = accounting.interval_start(second, 30, SYDNEY)
        # Wall-clock arithmetic always lands on the first pass, an hour early,
        # and would file every reading in the second pass under an interval
        # that closed an hour ago.
        self.assertEqual((second - start).total_seconds(), 0.0)

    def test_a_reading_an_hour_after_the_first_pass_started_is_a_new_interval(
        self,
    ) -> None:
        first, second = self._both_passes()
        first_start = accounting.interval_start(first, 30, SYDNEY)
        second_start = accounting.interval_start(second, 30, SYDNEY)
        self.assertEqual(
            (
                second_start.astimezone(UTC) - first_start.astimezone(UTC)
            ).total_seconds(),
            3600.0,
        )


class TestIntervalsAcrossTheMissingHour(unittest.TestCase):
    """The morning the clocks go forward, 02:30 never happens."""

    def test_the_interval_either_side_of_the_gap_is_found(self) -> None:
        before = datetime(2026, 10, 3, 15, 45, tzinfo=UTC)  # 01:45 AEST
        after = datetime(2026, 10, 3, 16, 15, tzinfo=UTC)  # 03:15 AEDT
        self.assertEqual(before.astimezone(SYDNEY).hour, 1)
        self.assertEqual(after.astimezone(SYDNEY).hour, 3)
        self.assertIsNotNone(accounting.interval_start(before, 30, SYDNEY))
        self.assertIsNotNone(accounting.interval_start(after, 30, SYDNEY))

    def test_the_two_are_not_the_same_interval(self) -> None:
        before = datetime(2026, 10, 3, 15, 45, tzinfo=UTC)
        after = datetime(2026, 10, 3, 16, 15, tzinfo=UTC)
        self.assertNotEqual(
            accounting.interval_key(before, 30, SYDNEY),
            accounting.interval_key(after, 30, SYDNEY),
        )

    def test_the_gap_is_half_an_hour_of_real_time(self) -> None:
        # 01:45 to 03:15 local is 30 minutes on the clock that matters.
        before = datetime(2026, 10, 3, 15, 45, tzinfo=UTC)
        after = datetime(2026, 10, 3, 16, 15, tzinfo=UTC)
        self.assertEqual((after - before).total_seconds(), 1800.0)


class TestIntervalCompletion(unittest.TestCase):
    """A partial interval is not a peak candidate."""

    def test_a_half_finished_interval_is_not_complete(self) -> None:
        start = datetime(2026, 5, 20, 14, 0, tzinfo=SYDNEY)
        moment = datetime(2026, 5, 20, 14, 20, tzinfo=SYDNEY)
        self.assertFalse(accounting.interval_is_complete(moment, start, 30))

    def test_a_finished_interval_is_complete(self) -> None:
        start = datetime(2026, 5, 20, 14, 0, tzinfo=SYDNEY)
        moment = datetime(2026, 5, 20, 14, 30, tzinfo=SYDNEY)
        self.assertTrue(accounting.interval_is_complete(moment, start, 30))

    def test_completion_is_measured_in_real_time_not_wall_clock(self) -> None:
        # 02:00 AEDT to 02:00 AEST is one real hour, though the wall clock
        # says no time passed at all.
        start = datetime(2026, 4, 4, 15, 30, tzinfo=UTC)
        moment = datetime(2026, 4, 4, 16, 0, tzinfo=UTC)
        self.assertTrue(accounting.interval_is_complete(moment, start, 30))

    def test_an_instantaneous_declaration_never_completes(self) -> None:
        start = datetime(2026, 5, 20, 14, 0, tzinfo=SYDNEY)
        moment = datetime(2026, 5, 20, 23, 0, tzinfo=SYDNEY)
        self.assertFalse(accounting.interval_is_complete(moment, start, 0))


class TestTheTwoBasesProduceDifferentMoney(unittest.TestCase):
    """Section 9 item 4, asserted directly."""

    def test_five_kilowatts_at_twenty_cents_over_31_days(self) -> None:
        flat = accounting.demand_cost(5.0, 0.20, "period", 31)
        per_day = accounting.demand_cost(5.0, 0.20, "day", 31)
        self.assertAlmostEqual(flat, 1.00, places=6)
        self.assertAlmostEqual(per_day, 31.00, places=6)

    def test_a_peak_of_nothing_costs_nothing_on_either_basis(self) -> None:
        self.assertEqual(accounting.demand_cost(0.0, 0.20, "day", 31), 0.0)
        self.assertEqual(accounting.demand_cost(0.0, 0.20, "period", 31), 0.0)

    def test_an_undeclared_price_costs_nothing(self) -> None:
        self.assertEqual(accounting.demand_cost(5.0, 0.0, "day", 31), 0.0)


class TestAverageDraw(unittest.TestCase):
    """The meter reports energy; a demand charge is priced on power."""

    def test_two_and_a_half_kilowatt_hours_in_half_an_hour_is_five_kilowatts(
        self,
    ) -> None:
        self.assertAlmostEqual(accounting.average_kw(2.5, 30), 5.0, places=6)

    def test_the_same_energy_over_an_hour_is_half_the_draw(self) -> None:
        self.assertAlmostEqual(accounting.average_kw(2.5, 60), 2.5, places=6)


class TestAllowanceKeys(unittest.TestCase):
    """Rule 8 and its sibling, asserted on the identity that enforces them."""

    def test_a_timed_allowance_belongs_to_the_slot_occurrence(self) -> None:
        today = accounting.allowance_key(
            "weekday.peak", "slot", 960, 1260, date(2026, 5, 20), 1
        )
        tomorrow = accounting.allowance_key(
            "weekday.peak", "slot", 960, 1260, date(2026, 5, 21), 1
        )
        self.assertNotEqual(today, tomorrow)

    def test_two_periods_naming_one_rate_on_one_day_are_two_slots(self) -> None:
        morning = accounting.allowance_key(
            "weekday.peak", "slot", 360, 540, date(2026, 5, 20), 1
        )
        evening = accounting.allowance_key(
            "weekday.peak", "slot", 960, 1260, date(2026, 5, 20), 1
        )
        self.assertNotEqual(morning, evening)

    def test_a_monthly_allowance_survives_midnight(self) -> None:
        today = accounting.allowance_key(
            "weekday.peak", "month", 960, 1260, date(2026, 5, 20), 12
        )
        tomorrow = accounting.allowance_key(
            "weekday.peak", "month", 960, 1260, date(2026, 5, 21), 12
        )
        self.assertEqual(today, tomorrow)

    def test_a_monthly_allowance_ignores_which_slot_it_was_drawn_in(self) -> None:
        morning = accounting.allowance_key(
            "weekday.peak", "month", 360, 540, date(2026, 5, 20), 12
        )
        evening = accounting.allowance_key(
            "weekday.peak", "month", 960, 1260, date(2026, 5, 20), 12
        )
        self.assertEqual(morning, evening)

    def test_a_monthly_allowance_resets_on_the_billing_cycle_day(self) -> None:
        before = accounting.allowance_key(
            "weekday.peak", "month", 960, 1260, date(2026, 6, 11), 12
        )
        on_the_day = accounting.allowance_key(
            "weekday.peak", "month", 960, 1260, date(2026, 6, 12), 12
        )
        self.assertNotEqual(before, on_the_day)

    def test_two_timetables_with_the_same_bare_name_are_kept_apart(self) -> None:
        weekday = accounting.allowance_key(
            "weekday.peak", "slot", 960, 1260, date(2026, 5, 20), 1
        )
        weekend = accounting.allowance_key(
            "weekend.peak", "slot", 960, 1260, date(2026, 5, 20), 1
        )
        self.assertNotEqual(weekday, weekend)


class TestTheLedger(unittest.TestCase):
    """What accumulates, and what resets it."""

    def test_rolling_an_allowance_period_starts_the_count_again(self) -> None:
        ledger = accounting.RateLedger("weekday.peak")
        ledger.roll_allowance("first")
        ledger.allowance_used_kwh = 8.0
        ledger.roll_allowance("second")
        self.assertEqual(ledger.allowance_used_kwh, 0.0)

    def test_the_closing_figure_is_kept_rather_than_discarded(self) -> None:
        ledger = accounting.RateLedger("weekday.peak")
        ledger.roll_allowance("first")
        ledger.allowance_used_kwh = 8.0
        ledger.roll_allowance("second")
        self.assertEqual(ledger.allowance_closed_kwh, 8.0)

    def test_rolling_to_the_same_period_changes_nothing(self) -> None:
        ledger = accounting.RateLedger("weekday.peak")
        ledger.roll_allowance("first")
        ledger.allowance_used_kwh = 8.0
        ledger.roll_allowance("first")
        self.assertEqual(ledger.allowance_used_kwh, 8.0)

    def test_a_new_cycle_clears_the_peak(self) -> None:
        ledger = accounting.RateLedger("weekday.peak")
        ledger.roll_cycle("2026-05-12")
        ledger.peak_kw = 5.0
        ledger.peak_at = datetime(2026, 5, 20, 17, 0, tzinfo=SYDNEY)
        ledger.roll_cycle("2026-06-12")
        self.assertEqual(ledger.peak_kw, 0.0)
        self.assertIsNone(ledger.peak_at)

    def test_a_new_cycle_clears_the_red_flag(self) -> None:
        ledger = accounting.RateLedger("weekday.peak")
        ledger.roll_cycle("2026-05-12")
        ledger.incomplete = True
        ledger.roll_cycle("2026-06-12")
        self.assertFalse(ledger.incomplete)

    def test_closing_an_interval_sets_a_higher_peak(self) -> None:
        ledger = accounting.RateLedger("weekday.peak")
        moment = datetime(2026, 5, 20, 17, 30, tzinfo=SYDNEY)
        ledger.interval_kwh = 2.5
        drawn = ledger.close_interval(moment, 30)
        self.assertAlmostEqual(drawn, 5.0, places=6)
        self.assertAlmostEqual(ledger.peak_kw, 5.0, places=6)
        self.assertEqual(ledger.peak_at, moment)

    def test_closing_a_smaller_interval_leaves_the_peak_alone(self) -> None:
        ledger = accounting.RateLedger("weekday.peak")
        first = datetime(2026, 5, 20, 17, 30, tzinfo=SYDNEY)
        ledger.interval_kwh = 2.5
        ledger.close_interval(first, 30)
        ledger.interval_kwh = 0.5
        ledger.close_interval(datetime(2026, 5, 20, 18, 0, tzinfo=SYDNEY), 30)
        self.assertAlmostEqual(ledger.peak_kw, 5.0, places=6)
        self.assertEqual(ledger.peak_at, first)

    def test_closing_an_interval_empties_it(self) -> None:
        ledger = accounting.RateLedger("weekday.peak")
        ledger.interval_kwh = 2.5
        ledger.close_interval(datetime(2026, 5, 20, 17, 30, tzinfo=SYDNEY), 30)
        self.assertEqual(ledger.interval_kwh, 0.0)


class TestTheNewRateFields(unittest.TestCase):
    """The three declarations, and what a plan stored before them loads as."""

    def _rate(self, **extra: object) -> object:
        raw = {"name": "Peak", "timetable": "Weekday", "import_cents": 30.0}
        raw.update(extra)
        return plan_module.Rate.from_dict(raw)

    def test_a_plan_stored_before_p35_gets_the_market_defaults(self) -> None:
        rate = self._rate()
        # Not zero. A zero interval reads as instantaneous and would count no
        # completed interval at all, so a demand charge on a migrated plan
        # would silently report a peak of nothing.
        self.assertEqual(rate.demand_interval, 30)
        self.assertEqual(rate.demand_basis, "day")
        self.assertEqual(rate.allowance_period, "slot")

    def test_the_declarations_round_trip_through_storage(self) -> None:
        rate = self._rate(
            demand_interval=15, demand_basis="period", allowance_period="month"
        )
        again = plan_module.Rate.from_dict(rate.as_dict())
        self.assertEqual(again.demand_interval, 15)
        self.assertEqual(again.demand_basis, "period")
        self.assertEqual(again.allowance_period, "month")

    def test_an_unknown_stored_token_falls_back_to_the_default(self) -> None:
        # Storage is not schema-checked on read. A token that reaches the
        # arithmetic and matches no constant would silently take the other
        # branch, which for a basis is the difference between $1 and $31.
        rate = self._rate(demand_basis="fortnightly", allowance_period="weekly")
        self.assertEqual(rate.demand_basis, "day")
        self.assertEqual(rate.allowance_period, "slot")

    def test_an_unknown_stored_interval_falls_back_to_the_default(self) -> None:
        self.assertEqual(self._rate(demand_interval=7).demand_interval, 30)
        self.assertEqual(self._rate(demand_interval="nonsense").demand_interval, 30)

    def test_instantaneous_is_a_permitted_declaration(self) -> None:
        self.assertEqual(self._rate(demand_interval=0).demand_interval, 0)

    def test_a_monthly_allowance_is_recognised_only_when_capped(self) -> None:
        uncapped = self._rate(allowance_period="month")
        capped = self._rate(allowance_period="month", rate_allowance_kwh=24.0)
        self.assertFalse(uncapped.counts_monthly_allowance)
        self.assertTrue(capped.counts_monthly_allowance)

    def test_declaring_the_period_is_what_makes_it_a_demand_rate(self) -> None:
        # The price may legitimately be zero — a household can know a window
        # is demand-metered before it knows what it is charged for it — and
        # the peak is still the fact the bill is built on.
        rate = self._rate(demand_period=True, demand_rate_per_kw_month=0.0)
        self.assertTrue(rate.has_demand_charge)
        self.assertFalse(self._rate().has_demand_charge)


class TestMergedCarriesTheNewFields(unittest.TestCase):
    """Rule 15. The model is the only thing that knows the key set."""

    def test_editing_a_name_does_not_delete_the_demand_declaration(self) -> None:
        stored = plan_module.Rate.from_dict(
            {
                "name": "Peak",
                "timetable": "Weekday",
                "import_cents": 30.0,
                "demand_period": True,
                "demand_interval": 15,
                "demand_basis": "period",
                "allowance_period": "month",
            }
        ).as_dict()
        edited = plan_module.merged(plan_module.Rate, stored, {"name": "Evening Peak"})
        self.assertEqual(edited["name"], "Evening Peak")
        self.assertEqual(edited["demand_interval"], 15)
        self.assertEqual(edited["demand_basis"], "period")
        self.assertEqual(edited["allowance_period"], "month")


if __name__ == "__main__":
    unittest.main()
