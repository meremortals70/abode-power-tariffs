# DR-036: Duplicating a timetable asks for new days and copies its rates

| | |
|---|---|
| Status | Accepted |
| Since | 0.8.10 (P37 Part B, 2026-08-23) |
| Origin | Finding A1c |
| Related | DR-004, DR-013 |

## Decision

Duplicating a timetable goes through the same step as adding one, so the
user gives the copy its own name and its own, different day coverage. Only
then are the source's rates and periods, both sides, copied onto it.

## Why

The old step copied periods but not rates, so the copy's periods named rates
it did not have and the save was refused. Checking that found a second fault:
it also copied the day coverage verbatim, so the copy collided with its
source and was never selected for any date. That had been dead since
`44072ae` (0.2.0 beta).

## Rejected

- **Deep-copy the timetable and rename it.** Both faults above.
- **Copy the days and ask the user to change them later.** Leaves a
  colliding plan in between.

## Consequences

There is nothing collision-prone left to copy. With rates nested in the
timetable (DR-013), they come across with it.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `config_flow.py:2327` - `async_step_day_pattern_duplicate` - routes through a real add
- `config_flow.py:2038` - `_duplicate_into` - copies rates and periods afterwards
- `tests/test_declaration.py:445` - `test_the_duplicate_actually_activates` - the dead-since-0.2.0 fault
