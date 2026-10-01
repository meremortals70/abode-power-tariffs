# DR-006: A gap flags the cycle incomplete and alerts at once

| | |
|---|---|
| Status | Accepted |
| Since | 0.8.8 (P35, stage four); restated in `ARCHITECTURE.md`, session eleven |
| Origin | P35, session seven |
| Related | DR-003, DR-007, DR-023 |

## Decision

When an input the integration depends on stops being readable (the import or
export energy sensor, or the holiday sensor), it flags itself incomplete
straight away and raises a repair issue the moment it happens. Recovery
clears the immediate flag, but the billing cycle stays marked incomplete
until it rolls over, and while it is, the output carries a red flag warning
that the data is incomplete.

## Why

A gap always makes the figures low, never high: a missed peak never
registered and missed energy was never counted. Recovery cannot retrieve
what was missed. Without a flag, an incomplete cycle and a complete one look
identical, and the integration gives a confident wrong answer for the rest of
the cycle.

## Rejected

- **Carry on quietly.** The failure is then discovered by chance, if at all.
- **Clear everything on recovery.** The cycle still has the hole in it.
- **Leave the fact in diagnostics only.** A detail the user has to go looking
  for is not an alert.

## Consequences

`Data complete` publishes two facts: whether an input is unreadable now, and
whether this cycle is unaffected. Every ledger is marked incomplete with it.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.** Every input
that becomes unreadable, the holiday sensor included, opens a gap, raises
the repair and marks the cycle and every ledger incomplete. The gap closes
only when every input is readable again. The cycle flag clears only when a
cycle rolls with no input down. `Data gap` is on for the rest of the cycle,
and the example dashboard cards show a red flag at the top while it is.

- `coordinator.py:869` - `_open_gap` - repair issue, flag down, cycle and ledgers marked
- `coordinator.py:904` - `_close_gap` - closes only when every input is readable
- `coordinator.py:368` - `_open_gap` - the holiday sensor opens a gap
- `coordinator.py:581` - `cycle_complete` - a new cycle starts incomplete if an input is down
- `binary_sensor.py:192` - `def is_on` - on for the rest of the cycle
- `tests/test_runtime.py:2188` - `TestHolidaySensorGaps` - the holiday gap, tested
