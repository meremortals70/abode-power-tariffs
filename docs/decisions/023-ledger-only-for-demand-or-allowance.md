# DR-023: A ledger exists only for demand or an allowance, one per rate, either side

| | |
|---|---|
| Status | Accepted |
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

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `accounting.py:220` - `class RateLedger` - the moving figures
- `coordinator.py:323` - `def ledger` - one per identifier
- `coordinator.py:306` - `ledger_for` - nothing for a rate no longer in the plan
- `coordinator.py:817` - `_accumulate_export_energy` - the export side
- `sensor.py:525` - `async_added_to_hass` - restored within its own period
