# DR-013: Rates are nested inside the timetable that owns them

| | |
|---|---|
| Status | Accepted; supersedes DR-012 |
| Since | By 0.9.10 (2026-08-27), session twelve |
| Origin | `ARCHITECTURE-GAPS.md` item 1 (the P38 direction), session eleven |
| Related | DR-012, DR-014, DR-015, DR-016 |

## Decision

A plan has no rates of its own; its timetables do. Every timetable holds four
things: import rates, import periods, export rates and export periods. A rate
belongs to one timetable and lives inside it. Nothing on a rate points back
at the timetable.

## Why

A timetable is one chunk of a plan's life: a set of days during which one set
of rates and periods applies. Periods already lived inside their timetable.
Rates living in a plan-wide list with a field saying which timetable they
were meant for (DR-012) put a fact about the timetable on the rate, where it
could go stale or fall back to the wrong rate, and every lookup had to
re-establish a relationship the storage shape could have held.

## Rejected

- **Fix the picker that exposed it (session eleven's first build).** Patches
  one symptom of the shape; binned.
- **Fix export only.** Import had the identical flaw.
- **Migrate the old shape.** Nothing is in production (DR-039).

## Consequences

Identity is structural: the only way to find a rate is to ask its timetable.
`Plan.rates` and `Plan.export_rates` remain as flattened views recomputed on
each access, not storage. Duplicating a timetable copies its rates with it
for free (DR-036).

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `plan.py:488` - `class DayPattern` - the four things inside a timetable
- `plan.py:515-516` - `export_rates` - rates stored on the timetable
- `plan.py:728` - `rate_by_name` - scoped lookup only; no fallback
- `plan.py:744` - `def rates` - a flattened view, not storage
