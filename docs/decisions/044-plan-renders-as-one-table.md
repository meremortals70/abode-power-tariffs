# DR-044: The plan renders as one table

| | |
|---|---|
| Status | Accepted |
| Since | 0.8.4 (P23) |
| Origin | Standing rule 12 |
| Related | DR-016, DR-043 |

## Decision

The plan renders as one table per timetable: time span, name as typed,
published identifier, price. There is no second block restating what the
first already said.

## Why

The plan rendered twice, a period table and then a rates block, so every
price appeared twice and the two could be read as different things.

## Rejected

- **A rates block beside the periods.** The duplication above.

## Consequences

Column widths are measured once across every timetable, so the tables line up
with each other. A rate no period uses is listed under "Not on any timetable".

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `strip.py:230` - `def render_plan` - one table per timetable
- `strip.py:31` - `def column_widths` - measured across the whole plan
