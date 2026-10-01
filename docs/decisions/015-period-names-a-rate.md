# DR-015: A period names a rate, carries no price, and the periods cover the day

| | |
|---|---|
| Status | Accepted |
| Since | First release |
| Origin | Design; confirmed in `ARCHITECTURE.md`, session eleven |
| Related | DR-004, DR-013 |

## Decision

A period is a slice of the day on one timetable: a start, an end, and the
name of one of that timetable's own rates. It has no price. Import periods
name import rates; export periods name export rates. The periods on one side
of one timetable cover the whole day, with no gaps and no overlaps.

## Why

A price lives in one place, the rate. Working out the cost at a moment is:
find the timetable in force, then the period on it, then the rate the period
names. If periods carried prices, the same price would be typed into every
period it applies to, and they would disagree.

## Rejected

- **A price on each period.** Two sources of truth for one price.
- **Allow uncovered minutes.** A minute nothing applies to has no true price.

## Consequences

Start is inclusive, end exclusive, and 1440 is "end of day", only ever an
end.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `plan.py:455` - `class Period` - start, end and a rate name
- `plan.py:899` - `def resolve` - timetable, then period, then rate
- `validate.py:29` - `validate_periods` - no gaps, no overlaps
