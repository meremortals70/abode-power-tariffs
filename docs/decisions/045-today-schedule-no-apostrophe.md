# DR-045: "Today schedule", with no apostrophe

| | |
|---|---|
| Status | Accepted |
| Since | By 0.9.10 (2026-08-27), session twelve |
| Origin | Live testing, session twelve |
| Related | None |

## Decision

The sensor publishing today's rates is named "Today schedule", not "Today's
schedule".

## Why

Home Assistant versions slugify an apostrophe differently, so the same
sensor got a different entity id depending on the version it was set up on,
and dashboard examples written against one id broke on the other.

## Rejected

- **Keep the apostrophe.** The entity id is not stable across versions.

## Consequences

The name reads slightly less naturally, and the entity id is the same
everywhere.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `strings.json:594` - `Today schedule` - the name
- `sensor.py:362` - `TodayScheduleSensor` - the sensor
