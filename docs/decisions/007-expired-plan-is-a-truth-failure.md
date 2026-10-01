# DR-007: A plan run past `valid_to` with no successor is a truth failure

| | |
|---|---|
| Status | Accepted |
| Since | By 0.9.10 (2026-08-27), session twelve |
| Origin | `ARCHITECTURE-GAPS.md` item 6, session eleven |
| Related | DR-005, DR-006 |

## Decision

A plan that reaches its `valid_to` with no successor in place gets the same
treatment as a data gap: the user is alerted the moment it happens, and the
same red flag that warns of incomplete data warns of this, for as long as the
plan sits expired with nothing set up to replace it.

## Why

Archiving is a decision: the user set the date knowing a new plan was ready.
A plan simply running out is different: nobody told the service to stop being
true. Before this, `plan_expired` was a boolean and a trace note, visible only
in diagnostics, while the component went on publishing an expired plan's
prices as if they were current.

## Rejected

- **Keep holding the expired plan silently (the code at 0.8.10).** The prices
  are no longer the truth and nothing says so.
- **Stop publishing.** Every consumer loses its price at once; the alert lets
  the user fix the cause instead.

## Consequences

The alert has to tell archiving apart from expiry, or every archived plan
alerts forever.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.** The repair is
raised only for a plan past its `valid_to` with no other plan for the same
import meter in force today; an archived plan with a successor raises
nothing. The same case turns `Data gap` on.

- `coordinator.py:389` - `plan_expired` - set on every refresh
- `coordinator.py:390` - `plan_replaced` - a successor for the same meter is in force
- `coordinator.py:960` - `_has_successor` - same import meter, active today
- `coordinator.py:931` - `_open_expired_issue` - raised only with no successor
- `coordinator.py:984` - `_close_expired_issue` - cleared otherwise
- `binary_sensor.py:192` - `def is_on` - expiry drives the flag
