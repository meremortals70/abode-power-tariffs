# DR-004: A plan can never be saved inconsistent

| | |
|---|---|
| Status | Accepted |
| Since | First release; extended to export by 0.8.10 |
| Origin | The fundamental precept |
| Related | DR-013, DR-015, DR-036 |

## Decision

A plan is refused unless it is internally consistent: every period names a
rate that exists on its own timetable, the periods on each side of each
timetable cover the whole day with no gaps or overlaps, every day of the year
is covered by some timetable, every declared allowance has a fallback that
resolves, and the validity range does not end before it starts.

## Why

A system of truth cannot publish a plan that contradicts itself, because
there is no true answer for it to report. A minute nothing applies to has no
price; a period naming a missing rate has no price either. Reporting zero
there is a fabrication (DR-018).

## Rejected

- **Save it and warn.** The warning is lost and the integration then has to
  invent an answer for every minute the plan does not cover.

## Consequences

Setup has a fix-it loop for a plan that fails on the last screen, rather than
throwing away everything typed. Some states that are inconvenient but not
contradictory, such as a capped rate spanning midnight, are warnings, not
refusals.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `validate.py:29` - `validate_periods` - each side covers the day
- `validate.py:74` - `validate_day_coverage` - every day has a timetable
- `validate.py:211` - `validate_rates` - names and fallbacks resolve
- `validate.py:295` - `validate_plan` - every check, every save
- `config_flow.py:1548` - `async_step_setup_invalid` - the fix-it loop
