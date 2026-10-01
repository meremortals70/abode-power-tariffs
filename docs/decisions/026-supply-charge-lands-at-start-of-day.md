# DR-026: The supply charge accumulates, landing in full at the start of each day

| | |
|---|---|
| Status | Accepted; supersedes DR-025 |
| Since | Accumulation at 0.8.8 (P35); full-day landing by 0.9.10 (2026-08-27) |
| Origin | Rule 11's revocation, session seven; `ARCHITECTURE-GAPS.md` item 5 |
| Related | DR-010, DR-011, DR-025 |

## Decision

The daily supply charge accumulates, today and across the billing cycle. The
whole day's charge lands the moment the local day begins, never prorated
across it. A plan's `monthly_charge` can stand alongside the daily charge or
instead of it, as the actual tariff requires.

## Why

That is how a retailer charges it: a day of connection costs the daily
charge whether the day is an hour old or nearly over. The first accrual
converted elapsed time into a fraction of the day against a fixed 1440
minutes, which over- or under-counts on the 23- and 25-hour days. Landing
once per local calendar day has no fraction to get wrong.

## Rejected

- **Prorate across the day (the code at 0.8.10).** Not how the charge
  works, and wrong on the transition days.
- **Keep it declared only (DR-025).** Cannot report the supply charge this
  cycle.
- **Force one of daily or monthly.** Some suppliers charge both.

## Consequences

`Supply charge this cycle` is whole days landed so far, today included,
counted in calendar days.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `coordinator.py:634` - `_refresh_supply_charge` - once per local day
- `coordinator.py:650` - `supply_charge_today` - the whole day, not a fraction
- `sensor.py:862` - `SupplyChargeTodaySensor` - published
- `sensor.py:880` - `SupplyChargeCycleSensor` - published for the cycle
