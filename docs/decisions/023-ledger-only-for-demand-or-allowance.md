# DR-023: A ledger exists only for demand or an allowance, one per rate, either side

| | |
|---|---|
| Status | Superseded in part by DR-051 |
| Since | Import at 0.8.9 (P35); export by 0.9.10 (2026-08-27) |
| Origin | Finding A5; `ARCHITECTURE-GAPS.md` item 4 |
| Related | DR-003, DR-016, DR-021, DR-022 |

## Decision

A ledger is created only for a rate that declares a demand charge or an
allowance, import or export. A rate with neither has no ledger. Where one
exists there is exactly one per rate, keyed on the four-segment identifier,
and nothing on one rate touches another's. Energy is credited to the rate it
was drawn under. A ledger is not part of the plan, but its numbers survive a
restart within the period they belong to, and are cleared when it ends.

## Why

A5: energy was credited to the slot being left and then thrown away when the
refresh zeroed the count on entering the next, so consumption just before
every boundary was lost. Keying a running total by bare name would collapse
two timetables' Peaks together, and before item 4 the ledger accepted only an
import `Rate`, so an export rate that declared demand or an allowance had
nowhere to count.

## Rejected

- **A ledger for every rate.** Empty records that look like facts.
- **One plan-level accumulator.** Cannot say which rate the energy was drawn
  under.
- **Lose the count on restart.** The integration could keep reporting the
  pre-allowance price after the cap was reached, or apply the fallback early.

## Consequences

A restored ledger for a rate an edit has since removed gets nothing, rather
than an orphan.

## In the code

Checked against: 0.9.12 + Builds 1-9 (2026-11-18). **Partly.** One per rate
still holds, keyed on the four-segment identifier, either side, and a rate with
neither a demand charge nor an allowance still has none. What the Decision does
not cover is the timetable's flat all-day feed-in declaration: it is not a rate,
declares a cap, and is now counted under `plan.timetable.export` (Build 6). That
is a second ledger identity the record does not name, so it is marked Partly
rather than quietly rewritten.

- `accounting.py:271` - `class RateLedger` - the moving figures
- `coordinator.py:399` - `def ledger` - one per identifier
- `coordinator.py:382` - `ledger_for` - nothing for a rate no longer in the plan
- `coordinator.py:1088` - `_accumulate_export_energy` - the export side
- `sensor.py:544` - `async_added_to_hass` - restored within its own period
- `plan.py:144` - `all_day_export_key` - the flat all-day declaration's own key, three segments
