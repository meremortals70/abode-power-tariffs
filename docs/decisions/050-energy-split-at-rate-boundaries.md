# DR-050: Energy across a rate boundary is split by real elapsed time

| | |
|---|---|
| Status | Accepted |
| Since | 0.9.12 + Builds 1-9 (2026-11-18) |
| Origin | Register entry 4 |
| Related | DR-003, DR-021, DR-022, DR-023 |

## Decision

The stretch between two meter readings is divided at every rate boundary
inside it, in proportion to the real elapsed time on each side. Each stretch
is credited to the rate in force just before its boundary. A late reading
whose tail falls inside an interval that has already closed raises the peak of
the interval it belongs to, rather than opening a new one.

## Why

An energy meter reports a total, never a timestamp. The delta between two
readings was credited in full to whichever rate happened to be in force when
the second reading arrived. A meter reporting every ten minutes therefore
mispriced however much was drawn on the other side of a boundary: over-pricing
the evening peak and under-counting a cap, both in the same direction, both
invisible.

The meter says how much, never when. Even attribution by elapsed time is the
only estimate available, and it is an estimate: the accumulating figures are
already declared as such in DR-021. Crediting the rate in force just before
each boundary is the reading that matches the price in force while the energy
was drawn.

## Rejected

- **Credit the whole delta to the rate in force when the reading arrives.**
  That was the defect. It charges the wrong price and the wrong cap in a
  predictable direction.
- **Ask the meter for timestamps per unit of energy.** A total counter has
  none to give; requiring a different meter would exclude every household
  this integration currently supports.
- **Split at demand and allowance boundaries too.** Those are bookkeeping
  windows inside a rate, not changes to the price. A stretch spanning several
  of them is credited to the interval containing its end, which is the only
  interval a late tail can still move.

## Consequences

A reading either side of a boundary now reaches both ledgers. A late tail
whose slot has already rolled is deliberately dropped rather than reviving a
closed figure. The walk is bounded: `next_boundary` covers at most three days
and one reading is split at most 256 times, after which it is credited where
it arrived. A meter reporting hours apart already carries that error.

The first reading after startup has no earlier reading to split against, so
its whole delta goes to the rate in force when it arrives.

## In the code

Checked against: 0.9.12 + Builds 1-9 (2026-11-18). **Conforms.**

- `coordinator.py:1134` - `_boundaries_between` - every boundary strictly inside the stretch
- `coordinator.py:95` - `_MAX_BOUNDARIES_PER_READING` - the 256-step ceiling
- `coordinator.py:1161` - `_credit_import_delta` - divides an import delta by real time
- `coordinator.py:1197` - `_credit_import_slice` - credits a stretch to its rate, including a late tail
- `coordinator.py:1247` - `_credit_export_delta` - the same on the export side
- `coordinator.py:1272` - `_credit_export_slice` - credits a stretch to its feed-in declaration
- `accounting.py:220` - `def split_delta` - the elapsed-time division
- `intervals.py:166` - `def next_boundary` - the real-instant boundary walk
