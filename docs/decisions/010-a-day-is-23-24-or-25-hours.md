# DR-010: A day is 23, 24 or 25 hours

| | |
|---|---|
| Status | Accepted |
| Since | First release |
| Origin | Standing rule 4 |
| Related | DR-009, DR-011, DR-026 |

## Decision

A day is 23, 24 or 25 hours long. A rate covering 02:00 to 03:00 is in force
for no time on the short day and two hours on the long one. "24 hours from
18:00" means 18:00 tomorrow. A count of days in a billing cycle is a count of
calendar days, not of 24-hour spans.

## Why

These follow from DR-009. Anything that assumes 1440 minutes in a day
over- or under-counts on the transition days. The prorated supply charge was
exactly that bug (DR-026).

## Rejected

- **Treat every day as 24 hours.** Wrong twice a year, in a way a test
  written the obvious way cannot catch.

## Consequences

A per-day demand charge multiplies by calendar days, so it agrees with the
retailer in the month a transition falls.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `accounting.py:69` - `days_in_cycle` - calendar days
- `accounting.py:283` - `midnight_instants` - the real start of a local day
- `coordinator.py:568-569` - `days_in_cycle` - per-day charges use calendar days
