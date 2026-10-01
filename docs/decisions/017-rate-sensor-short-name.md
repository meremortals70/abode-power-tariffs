# DR-017: The rate sensor shows a short name; the identifier is an attribute

| | |
|---|---|
| Status | Accepted |
| Since | By 0.9.10 (2026-08-27), session twelve |
| Origin | Live testing, session twelve |
| Related | DR-016 |

## Decision

The `Rate` sensor's state is the timetable and the rate's own name, the same
short form a per-rate entity's label uses. The full four-segment identifier
is published in its `scheduled_rate` attribute. A rate already named after
its timetable is not prefixed a second time.

## Why

The four-segment identifier is unambiguous but unreadable as a sensor state
on a dashboard. The state is what a human reads; the identifier is what a
machine keys on, and it is built independently of this sensor wherever it is
needed.

## Rejected

- **The full identifier as the state.** Correct and unreadable.
- **The bare rate name as the state.** Ambiguous across timetables (DR-016).
- **Always prefix the timetable.** "Every day Off Peak" on the "Every day"
  timetable is a common naming style, and would read "Every day Every day Off
  Peak".

## Consequences

Anything showing a rate to a human still has the identifier one attribute
away.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `sensor.py:319` - `RateSensor` - short state
- `sensor.py:355` - `scheduled_rate` - the identifier as an attribute
- `plan.py:143` - `display_name` - the short form, prefixed once at most
