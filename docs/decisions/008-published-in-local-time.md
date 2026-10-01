# DR-008: Everything is published in local time, with the offset

| | |
|---|---|
| Status | Accepted |
| Since | First release |
| Origin | Standing rule 2 |
| Related | DR-009, DR-010 |

## Decision

Every time the integration publishes, including the evcc forecast attribute,
is local time with its UTC offset. Never UTC. Time is walked in UTC internally
where correctness demands it; nothing leaves that way.

## Why

A tariff is written in the household's wall clock, and the people and
automations reading these values think in it. The offset makes each instant
unambiguous, including on the morning the clocks go back, when the same wall
time happens twice.

## Rejected

- **Publish UTC.** Correct but unreadable, and every consumer converts it
  back, which is a place for a timezone bug to hide.
- **Publish local time without the offset.** Ambiguous for one hour a year.

## Consequences

Internal comparisons normalise to UTC before subtracting, because Python
compares two aware datetimes sharing a tzinfo on the wall clock. That trap hid
a daylight-saving bug for a year.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `intervals.py:71-72` - `isoformat` - intervals published local, with offset
- `intervals.py:103` - `as_evcc_entry` - the evcc forecast, same form
- `intervals.py:189` - `astimezone(UTC)` - compared in UTC internally
